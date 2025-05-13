from django import template

from apps.quant.models import SARating

register = template.Library()


# Keeping those just in case I need them in the near future
# def get_type_score(value: dict, type_dict: dict):
#     return value[type_dict][INDEX_SCORE] if type_dict in value else -1
# def get_type_count(value: dict, type_tuple: tuple):
#     return value[type_tuple][INDEX_COUNT] if type_tuple in value else -1
# def get_type_rank(value: dict, type_tuple: tuple):
#     return value[type_tuple][INDEX_RANK] if type_tuple in value else "X"

@register.simple_tag
def get_types():
    return SARating.TYPES



# register.filter('get_type_score', get_type_score)
# register.filter('get_type_count', get_type_count)
# register.filter('get_type_rank', get_type_rank)
