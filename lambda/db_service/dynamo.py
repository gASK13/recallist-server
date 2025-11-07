import boto3
import os

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
item_table_name = os.getenv("ITEM_TABLE", "recallist_items")
item_table = dynamodb.Table(item_table_name)
api_keys_table_name = os.getenv("API_KEYS_TABLE", "recallist_api_keys")
api_keys_table = dynamodb.Table(api_keys_table_name)

# TBA methods to mainpulate dynamoDB
# make sure to make all topic storing / reloading CASE INSENSITIVE!