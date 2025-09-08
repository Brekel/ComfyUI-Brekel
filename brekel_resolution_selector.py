#
# Brekel Resolution Selector Node for ComfyUI
# Version: 1.0.0
#
# Author: Brekel - https://brekel.com
#
# This custom node provides a simple dropdown menu for selecting common image resolutions
# and an option to set the orientation (Landscape or Portrait).
#
# Key Features:
# - A curated list of common resolutions for Flux, Qwen, SDXL, SD 1.5, and Video.
# - A dropdown to switch between Landscape and Portrait orientation.
# - A dedicated input for the number of frames for video workflows.
# - Outputs separate integer values for width, height, and number of frames.

# --- PRESET RESOLUTIONS ---
# A dictionary of common resolutions. The key is the display name in the UI and the value is a tuple of (width, height).
RESOLUTION_PRESETS = {
    # --- Flux / Qwen Resolutions (High-Res, trained at 1024x1024) ---
    "Flux/Qwen Square (1024 x 1024)": (1024, 1024),
    "Flux/Qwen Portrait 3:4 (896 x 1152)": (896, 1152),
    "Flux/Qwen Landscape 4:3 (1152 x 896)": (1152, 896),
    "Flux/Qwen Widescreen 16:9 (1344 x 768)": (1344, 768),

    # --- SDXL Resolutions (common aspect ratios) ---
    "SDXL Square (1024 x 1024)": (1024, 1024),
    "SDXL Portrait 4:5 (896 x 1152)": (896, 1152),
    "SDXL Landscape 5:4 (1088 x 896)": (1088, 896),
    "SDXL Landscape 4:3 (1152 x 896)": (1152, 896),
    "SDXL Portrait 2:3 (832 x 1216)": (832, 1216),
    "SDXL Landscape 3:2 (1216 x 832)": (1216, 832),
    "SDXL Widescreen 16:9 (1344 x 768)": (1344, 768),
    "SDXL Ultrawide 21:9 (1536 x 640)": (1536, 640),

    # --- SD 1.5 Resolutions ---
    "SD 1.5 Square (512 x 512)": (512, 512),
    "SD 1.5 Portrait (512 x 768)": (512, 768),
    "SD 1.5 Landscape (768 x 512)": (768, 512),

    # --- Video Resolutions (Standard 16:9 unless specified) ---
    "Video 480p (832 x 480)": (832, 480),
    "Video 540p (960 x 544)": (960, 544),
    "Video 720p HD (1280 x 720)": (1280, 720),
    "Video 1080p FHD (1920 x 1080)": (1920, 1080),
}


class BrekelResolutionSelector:
    """
    Brekel Resolution Selector

    A node that allows users to select a preset resolution and orientation,
    outputting the corresponding width, height, and number of frames as integers.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        """
        Defines the input widgets for the node.
        """
        # Get the list of preset names for the dropdown
        preset_names = list(RESOLUTION_PRESETS.keys())
        
        return {
            "required": {
                "resolution": (preset_names, {
                    "default": "Video 480p (832 x 480)",
                    "tooltip": "Select a common resolution preset for images or video."
                }),
                "orientation": (["Landscape", "Portrait"], {
                    "default": "Landscape",
                    "tooltip": "Choose the orientation. This will swap width and height if needed."
                }),
                "num_frames": ("INT", {
                    "default": 121, 
                    "min": 1, 
                    "max": 10000, 
                    "step": 4, 
                    "tooltip": "Number of frames to generate. Primarily for video workflows."
                }),
            }
        }

    # --- Node configuration for ComfyUI ---
    CATEGORY = "Brekel"
    FUNCTION = "get_resolution"
    RETURN_TYPES = ("INT", "INT", "INT",)
    RETURN_NAMES = ("width", "height", "num_frames",)
    OUTPUT_NODE = False

    def get_resolution(self, resolution: str, orientation: str, num_frames: int):
        """
        This function retrieves the selected resolution, adjusts it based on the
        chosen orientation, and passes through the number of frames.
        
        Args:
            resolution (str): The string name of the selected preset from the dropdown.
            orientation (str): The selected orientation ("Landscape" or "Portrait").
            num_frames (int): The number of frames specified by the user.
            
        Returns:
            A tuple containing three integers: (width, height, num_frames).
        """
        # Look up the base width and height from our presets dictionary
        width, height = RESOLUTION_PRESETS[resolution]

        # Determine the inherent orientation of the preset
        is_preset_landscape = width > height
        is_preset_portrait = height > width

        # If the user wants Portrait but the preset is Landscape, swap them
        if orientation == "Portrait" and is_preset_landscape:
            final_width, final_height = height, width
        # If the user wants Landscape but the preset is Portrait, swap them
        elif orientation == "Landscape" and is_preset_portrait:
            final_width, final_height = height, width
        # Otherwise, the orientation matches or it's a square, so return as is
        else:
            final_width, final_height = width, height

        return (final_width, final_height, num_frames)


# --- ComfyUI Node Registration ---
NODE_CLASS_MAPPINGS = {"BrekelResolutionSelector": BrekelResolutionSelector}
NODE_DISPLAY_NAME_MAPPINGS = {"BrekelResolutionSelector": "Brekel Resolution Selector"}