# /app/core/templates.py | Updated: 2026-05-26 17:00 MDT
import os
from fastapi.templating import Jinja2Templates

# 1. Get the absolute path of 'app/core/'
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. Go up one level to 'app/' and enter 'templates/'
# This builds the real path: C:\powercore\app\templates
templates_path = os.path.normpath(os.path.join(current_dir, "..", "templates"))

# 3. Robust initialization
jinja = Jinja2Templates(directory=templates_path)

# Confirmation for console
print(f"INFO: PowerCore templates location: {templates_path}")
