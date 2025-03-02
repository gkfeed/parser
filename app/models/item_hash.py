from tortoise import fields
from tortoise.models import Model


class ItemHash(Model):
    hash = fields.TextField()
