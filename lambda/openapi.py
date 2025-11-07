import yaml
from main import app  # Import your FastAPI app

# Generate the OpenAPI schema
openapi_schema = app.openapi()

# Force OpenAPI version to 3.0.0
openapi_schema["openapi"] = "3.0.0"

# Add a custom info section
openapi_schema["info"] = {
    "title": "Recallist API",
    "description": "API for the Recallist MCP server",
    "version": "1.0.0"
}

# Add API Key security scheme
components = openapi_schema.setdefault("components", {})
security_schemes = components.setdefault("securitySchemes", {})

security_schemes["CognitoAuthorizer"] = {
    "type": "apiKey",
    "name": "Authorization",
    "in": "header",
    "x-amazon-apigateway-authtype" : "cognito_user_pools",
    "x-amazon-apigateway-authorizer": {
        "type": "cognito_user_pools",
        "providerARNs": [
            "${cognito_user_pool_arn}"  # Replace this when deploying
        ]
    }
}

security_schemes["ApiKeyAuth"] = {
    "type": "apiKey",
    "name": "x-api-key",
    "in": "header"
}

# Optional: ensure API key source (header)
openapi_schema["x-amazon-apigateway-api-key-source"] = "HEADER"


# Rename schemas to remove hyphens
if "schemas" in components:
    updated = {}
    for schema_name, schema_content in components["schemas"].items():
        # Replace hyphens with empty strings to make names alphanumeric
        new_name = schema_name.replace("-", "")
        updated[new_name] = schema_content

        # Update references in the paths
        for path_item in openapi_schema["paths"].values():
            for method_item in path_item.values():
                rb = method_item.get("requestBody", {})
                app_json = rb.get("content", {}).get("application/json", {})
                if "$ref" in app_json.get("schema", {}) and app_json["schema"]["$ref"].endswith(f"/{schema_name}"):
                    app_json["schema"]["$ref"] = app_json["schema"]["$ref"].replace(schema_name, new_name)
                for resp in method_item.get("responses", {}).values():
                    app_json_resp = resp.get("content", {}).get("application/json", {})
                    schema = app_json_resp.get("schema", {})
                    if "$ref" in schema and schema["$ref"].endswith(f"/{schema_name}"):
                        schema["$ref"] = schema["$ref"].replace(schema_name, new_name)

    components["schemas"] = updated

# Add security and integration to each method
for path, methods in openapi_schema["paths"].items():
    for method, details in methods.items():
        # Add Cognito security requirement
        details["security"] = [
            {"CognitoAuthorizer": []},
            {"ApiKeyAuth": []}
        ]

        # Add x-amazon-apigateway-integration
        details["x-amazon-apigateway-integration"] = {
            "uri": "${lambda_arn}",
            "httpMethod": "POST",
            "type": "aws_proxy"
        }

        # Simplify responses
        if "responses" in details:
            for status_code, response in details["responses"].items():
                response["content"] = {
                    "application/json": {}
                }



# Save the schema to a YAML file
with open("openapi.yaml", "w") as f:
    yaml.dump(openapi_schema, f, default_flow_style=False)

print("OpenAPI schema has been generated and saved to openapi.yaml")