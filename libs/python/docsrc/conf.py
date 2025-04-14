# libs/python/docsrc/conf.py
import os
import sys

# -- Path setup --------------------------------------------------------------
# Add the 'src' directory of your library to sys.path so Sphinx can find it.
# Adjust the path '../..' based on the location of conf.py relative to src/
sys.path.insert(0, os.path.abspath('../../src'))

# -- Project information -----------------------------------------------------
project = 'Sidekick Python Library'
copyright = '2025, Enjan Chou' # Replace with your name/year
author = 'Enjan Chou' # Replace with your name

# Attempt to get the version dynamically from your _version.py
try:
    from sidekick._version import __version__
    version = __version__
    release = __version__
except ImportError:
    print("Warning: Could not import sidekick._version to determine version.")
    version = '0.0.0' # Fallback version
    release = '0.0.0'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',      # Core library to pull documentation from docstrings
    'sphinx.ext.napoleon',     # Support for NumPy and Google style docstrings (optional but good)
    'sphinx.ext.intersphinx',  # Link to other projects' documentation (e.g., Python)
    'sphinx.ext.viewcode',     # Add links to source code from documentation
    'sphinx.ext.githubpages', # Helps with GitHub Pages deployment (optional)
]

# Autodoc settings (optional customization)
autodoc_member_order = 'bysource' # Order members by source code order
# autodoc_default_options = {
#     'members': True,
#     'undoc-members': True, # Include members without docstrings (use with caution)
#     'private-members': False,
#     'special-members': '__init__', # Document __init__ methods
#     'show-inheritance': True,
# }

# Napoleon settings (if using Google/NumPy style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False # Set to True if using NumPy style
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True

# Intersphinx configuration (example for linking to Python docs)
intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

templates_path = ['_templates'] # Directory for custom templates (usually not needed initially)
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store'] # Files/dirs to ignore

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme' # Use the Read the Docs theme
# html_logo = "_static/logo.png" # Optional: Add a logo file here
html_static_path = ['_static'] # Directory for static files (CSS, images) within docsrc
html_theme_options = {
    # 'logo_only': False,
    # 'display_version': True,
    # 'prev_next_buttons_location': 'bottom',
    # 'style_external_links': False,
    # 'vcs_pageview_mode': '',
    # 'style_nav_header_background': 'white',
    # # Toc options
    # 'collapse_navigation': True,
    # 'sticky_navigation': True,
    # 'navigation_depth': 4,
    # 'includehidden': True,
    # 'titles_only': False
}

# -- Options for LaTeX output (if needed) ------------------------------------
latex_elements = {
    # 'papersize': 'letterpaper',
    # 'pointsize': '10pt',
    # 'preamble': '',
    # 'figure_align': 'htbp',
}
