import yaml
import copy
from main import app  # Import your FastAPI app

# Generate the OpenAPI schema from FastAPI
openapi_schema = app.openapi()

# Force OpenAPI version to 3.0.0
openapi_schema["openapi"] = "3.0.0"

# Add a custom info section
openapi_schema["info"] = {
    "title": "Recallist API",
    "description": "API for the Recallist MCP server allowing agents to store a list of items and recall them later, including marking as resolved and fetching random items.",
    "version": "1.0.0"
}

# Ensure components exists
components = openapi_schema.setdefault("components", {})

# Rename schemas to remove hyphens (keep model refs readable)
if "schemas" in components and isinstance(components.get("schemas"), dict):
    updated = {}
    for schema_name, schema_content in components["schemas"].items():
        new_name = schema_name.replace("-", "")
        updated[new_name] = schema_content

        # Update all $ref occurrences in request/response bodies
        for path_item in openapi_schema.get("paths", {}).values():
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

# Create a GPT-friendly copy BEFORE adding AWS API Gateway specifics
gpt_schema = copy.deepcopy(openapi_schema)

# Set GPT spec to OpenAPI 3.1.0 (AWS API Gateway requires 3.0.0, which we keep on the main schema)
gpt_schema["openapi"] = "3.1.0"
# Optionally declare JSON Schema dialect for 3.1 (harmless if consumers ignore it)
gpt_schema["jsonSchemaDialect"] = "https://json-schema.org/draft/2020-12/schema"

# Strip authorization/security from GPT schema and ensure operationIds and rich content remain
# - Remove securitySchemes, security requirements, and vendor extensions
if "components" in gpt_schema and isinstance(gpt_schema["components"], dict):
    gpt_schema["components"].pop("securitySchemes", None)

for path, methods in gpt_schema.get("paths", {}).items():
    for method, details in methods.items():
        # Remove any security requirements if present
        if isinstance(details, dict):
            details.pop("security", None)
            # Remove vendor-specific integrations if they sneak in
            details.pop("x-amazon-apigateway-integration", None)
            # Ensure operationId exists
            if "operationId" not in details or not details.get("operationId"):
                safe_path = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
                details["operationId"] = f"{method}_{safe_path}" if safe_path else method

# Save GPT-friendly schema
with open("openapi.gpt.yaml", "w") as gf:
    yaml.dump(gpt_schema, gf, default_flow_style=False)

# Now augment the original schema with API Gateway security and integration
security_schemes = components.setdefault("securitySchemes", {})
# Define a single REQUEST authorizer that accepts either Authorization (Cognito JWT) or x-api-key
security_schemes["EitherOrAuthorizer"] = {
    "type": "apiKey",
    "name": "Authorization",
    "in": "header",
    "x-amazon-apigateway-authtype": "custom",
    "x-amazon-apigateway-authorizer": {
        "type": "request",
        "identitySource": "method.request.header.Authorization",
        "authorizerUri": "${authorizer_uri}"
    }
}

# Apply security and Lambda proxy integration to each method; simplify response contents for APIGW
for path, methods in openapi_schema.get("paths", {}).items():
    for method, details in methods.items():
        if not isinstance(details, dict):
            continue
        # Require our custom authorizer on all methods
        details["security"] = [{"EitherOrAuthorizer": []}]
        # Lambda proxy integration
        details["x-amazon-apigateway-integration"] = {
            "uri": "${lambda_arn}",
            "httpMethod": "POST",
            "type": "aws_proxy"
        }
        # Simplify responses for API Gateway import (content definitions often ignored)
        if "responses" in details and isinstance(details["responses"], dict):
            for status_code, response in details["responses"].items():
                if isinstance(response, dict):
                    response["content"] = {"application/json": {}}

# Save the API Gateway–ready schema
with open("openapi.yaml", "w") as f:
    yaml.dump(openapi_schema, f, default_flow_style=False)

print("OpenAPI schemas generated: openapi.yaml (API Gateway) and openapi.gpt.yaml (GPT-friendly)")