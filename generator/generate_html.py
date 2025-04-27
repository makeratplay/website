from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import sys
import json





# Read the first argument passed via the command line
if len(sys.argv) < 2:
    print("Usage: python generate_html.py <path_to_json_file>")
    sys.exit(1)

json_file_path = sys.argv[1]

try:
    with open(json_file_path, 'r') as json_file:
        try:
            data = json.load(json_file)
        except json.JSONDecodeError as e:    
            print(f"Invalid JSON file: {json_file_path}: {e}")
            sys.exit(1)
except FileNotFoundError:
    print(f"File not found: {json_file_path}")
    sys.exit(1)

template_file = "../" + data["template"]

# Load the template file
# Set up the Jinja2 environment
template_dir = '.'  # Directory where the template file is located
env = Environment(loader=FileSystemLoader(template_dir))

try:
    template = env.get_template(template_file)
except TemplateNotFound:
    print(f"Template File not found: {template_file}")
    sys.exit(1)
    
# Render the template with data
output = template.render(data)

# Save the rendered HTML to a file
output_file = "../" + data["file"]
with open(output_file, 'w') as f:
    f.write(output)

print(f"Static HTML file generated: {output_file}")
