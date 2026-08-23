# Import the mappings from the new prompt chooser node
from .brekel_prompt_chooser import NODE_CLASS_MAPPINGS as CHOOSER_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as CHOOSER_NAME_MAPPINGS

# Import the mappings from the first node file using aliases to avoid name conflicts
from .brekel_auto_prompt_generator import NODE_CLASS_MAPPINGS as AUTO_PROMPT_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as AUTO_PROMPT_NAME_MAPPINGS

# Import the mappings from the second node file using different aliases
from .brekel_enhance_prompt import NODE_CLASS_MAPPINGS as ENHANCE_PROMPT_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as ENHANCE_PROMPT_NAME_MAPPINGS

# Import the mappings from the new resolution selector node
from .brekel_resolution_selector import NODE_CLASS_MAPPINGS as RESOLUTION_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as RESOLUTION_NAME_MAPPINGS

# Import the mappings from the new load image node
from .brekel_load_image import NODE_CLASS_MAPPINGS as LOAD_IMAGE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as LOAD_IMAGE_NAME_MAPPINGS

# Import the mappings from the new save image node
from .brekel_save_image import NODE_CLASS_MAPPINGS as SAVE_IMAGE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as SAVE_IMAGE_NAME_MAPPINGS

# Import the mappings from the directory-based lora loader node
from .brekel_lora_loader import NODE_CLASS_MAPPINGS as LORA_LOADER_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as LORA_LOADER_NAME_MAPPINGS

# Merge the class mappings from all files into one dictionary
NODE_CLASS_MAPPINGS = {
    **CHOOSER_CLASS_MAPPINGS,
    **AUTO_PROMPT_CLASS_MAPPINGS,
    **ENHANCE_PROMPT_CLASS_MAPPINGS,
    **RESOLUTION_CLASS_MAPPINGS,
    **LOAD_IMAGE_CLASS_MAPPINGS,
    **SAVE_IMAGE_CLASS_MAPPINGS,
    **LORA_LOADER_CLASS_MAPPINGS,
}

# Merge the display name mappings from all files into one dictionary
NODE_DISPLAY_NAME_MAPPINGS = {
    **CHOOSER_NAME_MAPPINGS,
    **AUTO_PROMPT_NAME_MAPPINGS,
    **ENHANCE_PROMPT_NAME_MAPPINGS,
    **RESOLUTION_NAME_MAPPINGS,
    **LOAD_IMAGE_NAME_MAPPINGS,
    **SAVE_IMAGE_NAME_MAPPINGS,
    **LORA_LOADER_NAME_MAPPINGS,
}

# Tell ComfyUI where to find frontend JS extensions (viewport lock, etc.)
WEB_DIRECTORY = "./js"

# This tells Python what variables to export from this module
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]