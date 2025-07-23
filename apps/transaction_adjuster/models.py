from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from decimal import Decimal
from constants import CURRENCY_CAD, CURRENCY_USD, TRANSACTION_BUY, TRANSACTION_SELL


def update_adjusted_values_for_symbol(symbol: str):
    """
    Recalculate adjusted values for all transactions with the given symbol.
    This takes into account all stock splits for the symbol.
    """
    # Get all transactions for this symbol
    transactions = StockTransaction.objects.filter(symbol=symbol).order_by('date')

    # Process each transaction
    for transaction in transactions:
        transaction.calculate_adjusted_values()
        transaction.save(update_fields=['adjusted_quantity', 'adjusted_price_per_share'])


class StockTransaction(models.Model):
    CURRENCY_CHOICES = [
        (CURRENCY_USD, 'USD'),
        (CURRENCY_CAD, 'CAD'),
    ]
    
    TRANSACTION_TYPE_CHOICES = [
        (TRANSACTION_BUY, 'Buy'),
        (TRANSACTION_SELL, 'Sell'),
    ]
    
    date = models.DateField()
    symbol = models.CharField(max_length=10)
    quantity = models.IntegerField()
    adjusted_quantity = models.IntegerField(null=True, blank=True)
    price_per_share = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    adjusted_price_per_share = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    total_cost = models.DecimalField(max_digits=15, decimal_places=3, null=True, blank=True)
    notes = models.TextField(blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=CURRENCY_USD)
    type = models.CharField(max_length=4, choices=TRANSACTION_TYPE_CHOICES, default=TRANSACTION_BUY)

    def clean(self):
        """Ensure at least one of price_per_share or total_cost is provided."""
        if self.price_per_share is None and self.total_cost is None:
            raise ValidationError("Either price per share or total cost must be provided.")
        
        # Calculate the missing field if one is provided
        if self.price_per_share is None and self.total_cost is not None and self.quantity:
            self.price_per_share = self.total_cost / self.quantity
        elif self.total_cost is None and self.price_per_share is not None and self.quantity:
            self.total_cost = self.price_per_share * self.quantity

    def calculate_adjusted_values(self):
        """Calculate adjusted values based on stock splits after this transaction"""
        # Start with original values
        self.adjusted_quantity = self.quantity
        original_price = self.price_per_share if self.price_per_share else (self.total_cost / self.quantity)
        self.adjusted_price_per_share = original_price
        
        # Apply all splits that happened after this transaction
        splits = StockSplit.objects.filter(symbol=self.symbol, date__gt=self.date).order_by('date')
        
        for split in splits:
            # For a 2:1 split (split=2.0), quantity doubles and price halves
            # For a 1:2 reverse split (split=0.5), quantity halves and price doubles
            self.adjusted_quantity = int(self.adjusted_quantity * Decimal(split.split))
            self.adjusted_price_per_share = self.adjusted_price_per_share / Decimal(split.split)

    def save(self, *args, **kwargs):
        # Convert symbol to uppercase
        self.symbol = self.symbol.upper()
        
        self.clean()
        self.calculate_adjusted_values()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.symbol}: {self.quantity}"
    
    class Meta:
        ordering = ['-date', 'symbol']


class StockSplit(models.Model):
    symbol = models.CharField(max_length=10, db_index=True)
    date = models.DateField()
    split = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="Split ratio (e.g., 2.0 for a 2:1 split, 0.5 for a 1:2 reverse split)"
    )
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        # Convert symbol to uppercase
        self.symbol = self.symbol.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.symbol}: {self.split}"

    class Meta:
        ordering = ['-date', 'symbol']


@receiver(post_save, sender=StockSplit)
def stock_split_saved(sender, instance, **kwargs):
    """Handler that triggers when a StockSplit is created or updated"""
    update_adjusted_values_for_symbol(instance.symbol)


@receiver(post_delete, sender=StockSplit)
def stock_split_deleted(sender, instance, **kwargs):
    """Handler that triggers when a StockSplit is deleted"""
    update_adjusted_values_for_symbol(instance.symbol)