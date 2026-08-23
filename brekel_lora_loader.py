#
# Brekel Lora Loader Node for ComfyUI
# Version: 1.0.0
#
# Author: Brekel - https://brekel.com
#
# This node loads LoRAs from a specified custom directory instead of the default list.
# It selects the LoRA based on an index integer, allowing for "increment", "decrement", 
# "randomize" controls in the ComfyUI widget.

import os
import comfy.utils
import comfy.sd
import folder_paths

class BrekelLoraLoader:
    def __init__(self):
        self.loaded_lora = None

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "LORA_NAME")
    FUNCTION = "load_lora"
    CATEGORY = "loaders"

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "folder_path": ("STRING", {"default": "", "multiline": False, "placeholder": "C:/path/to/my/loras"}),
                # control_after_generate adds the (fixed / increment / decrement /
                # randomize) box to this INT widget, so queued runs can step through
                # or randomly pick loras in the folder.
                "lora_index": ("INT", {"default": 0, "min": 0, "max": 999999, "step": 1, "control_after_generate": True}),
                "strength_model": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_clip": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
            }
        }

    def load_lora(self, model, clip, folder_path, lora_index, strength_model, strength_clip):
        # Optimization: If strength is 0, pass through without loading
        if strength_model == 0 and strength_clip == 0:
            return (model, clip, "None")

        # Handle empty path input - fallback to default lora path if necessary, 
        # though usually users want a specific custom path here.
        if folder_path.strip() == "":
            folder_path = folder_paths.get_folder_paths("loras")[0]
        
        if not os.path.isabs(folder_path):
            folder_path = os.path.abspath(folder_path)

        if not os.path.isdir(folder_path):
            print(f"Brekel Lora Loader: Directory not found: {folder_path}")
            return (model, clip, "None")

        # Get list of valid lora files
        valid_extensions = {'.safetensors', '.ckpt', '.pt'}
        files = [f for f in os.listdir(folder_path) 
                 if os.path.isfile(os.path.join(folder_path, f)) 
                 and os.path.splitext(f)[1].lower() in valid_extensions]
        
        files.sort() # Ensure consistent order for indexing

        if not files:
            print(f"Brekel Lora Loader: No LoRA models found in: {folder_path}")
            return (model, clip, "None")

        # Calculate index using modulo so it loops if index > file count
        actual_index = lora_index % len(files)
        lora_name = files[actual_index]
        lora_path = os.path.join(folder_path, lora_name)

        # Caching logic to prevent reloading the same file unnecessarily
        lora = None
        if self.loaded_lora is not None:
            if self.loaded_lora[0] == lora_path:
                lora = self.loaded_lora[1]
            else:
                self.loaded_lora = None

        if lora is None:
            try:
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                self.loaded_lora = (lora_path, lora)
            except Exception as e:
                print(f"Brekel Lora Loader: Error loading LoRA {lora_name}: {e}")
                return (model, clip, "Error")

        # Apply LoRA
        model_lora, clip_lora = comfy.sd.load_lora_for_models(model, clip, lora, strength_model, strength_clip)

        lora_name_no_ext = os.path.splitext(lora_name)[0]
        return (model_lora, clip_lora, lora_name_no_ext)

# ComfyUI mappings
NODE_CLASS_MAPPINGS = {
    "BrekelLoraLoader": BrekelLoraLoader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BrekelLoraLoader": "Brekel Lora Loader (Directory)"
}