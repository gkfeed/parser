from tortoise import fields
from tortoise.models import Model


class Feed(Model):
    id = fields.IntField(pk=True)
    title = fields.TextField()
    url = fields.TextField()
    type = fields.TextField()
