# Import the mappings from the new prompt chooser node
from .brekel_prompt_chooser import NODE_CLASS_MAPPINGS as CHOOSER_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as CHOOSER_NAME_MAPPINGS

# Import the mappings from the first node file using aliases to avoid name conflicts
from .brekel_auto_prompt_generator import NODE_CLASS_MAPPINGS as AUTO_PROMPT_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as AUTO_PROMPT_NAME_MAPPINGS

# Import the mappings from the second node file using different aliases
from .brekel_enhance_prompt import NODE_CLASS_MAPPINGS as ENHANCE_PROMPT_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as ENHANCE_PROMPT_NAME_MAPPINGS

# Import the mappings from the new resolution selector node
from .brekel_resolution_selector import NODE_CLASS_MAPPINGS as RESOLUTION_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as RESOLUTION_NAME_MAPPINGS

# Merge the class mappings from all files into one dictionary
NODE_CLASS_MAPPINGS = {
    **CHOOSER_CLASS_MAPPINGS,
    **AUTO_PROMPT_CLASS_MAPPINGS,
    **ENHANCE_PROMPT_CLASS_MAPPINGS,
    **RESOLUTION_CLASS_MAPPINGS,
}

# Merge the display name mappings from all files into one dictionary
NODE_DISPLAY_NAME_MAPPINGS = {
    **CHOOSER_NAME_MAPPINGS,
    **AUTO_PROMPT_NAME_MAPPINGS,
    **ENHANCE_PROMPT_NAME_MAPPINGS,
    **RESOLUTION_NAME_MAPPINGS,
}

# This tells Python what variables to export from this module
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]