#
# Brekel Auto Prompt Generator Node for ComfyUI
# Version: 1.2.0
#
# Author: Brekel - https://brekel.com
#
# This custom node generates prompts by combining user-defined prefixes, postfixes, and random lines from text files.
#
# Key Features:
# - Allows dynamic selection of text files to pick random lines from.
# - Reads from text files located in the 'ComfyUI/custom_nodes/ComfyUI-Brekel/auto_prompt_generator' subfolder.
# - Supports static prompts.
# - Handles multiple text files with a seed for randomization. 
# - Provides options for prefix, postfix, and delimiter customization.
# - Cleans up whitespace if desired.
#
#
# Release log:
#
# v1.2.0:
# - lines are picked from a shuffled order per file, with the seed control on 'increment' every line comes up once before any repeats
# - each file gets its own order, so files of similar length no longer pick the same line number for a given seed
#
# v1.1.0:
# - node now shows the prompt it generated on the node itself after it has run
#


# --- CONFIGURATION CONSTANT ---
# Define the subfolder name where text files are stored.
SUBFOLDER_NAME = "auto_prompt_generator"


import os

from .brekel_shuffle import shuffled_index

# import block to communicate with the frontend
try:
    from server import PromptServer
except ImportError:
    # If the server is not available (e.g., in a headless environment)  create a dummy class to prevent errors.
    class PromptServer:
        instance = None


# --- HELPER FUNCTIONS ---
def get_txt_files(sub_dir=SUBFOLDER_NAME):
    """
    Finds all .txt files in a subdirectory relative to this script.
    Assumes the directory exists as part of the repository.
    """
    script_dir = os.path.dirname(__file__)
    target_dir = os.path.join(script_dir, sub_dir)

    # The directory is expected to exist. If not, it's an installation issue.
    if not os.path.isdir(target_dir):
        print(f"[Brekel Node Error] Directory not found: '{target_dir}'")
        print(f"  Please ensure the node was installed correctly or reinstall it via the ComfyUI Manager.")
        return ["None"] # Return a list with 'None' to prevent UI from breaking

    files = ["None"]
    try:
        for f in os.listdir(target_dir):
            if f.endswith(".txt") and os.path.isfile(os.path.join(target_dir, f)):
                files.append(f)
        files.sort()
    except Exception as e:
        print(f"[Brekel Node Error] Could not list .txt files in '{target_dir}': {e}")
    return files


def pick_random_line_from_file(file_path, seed_value, salt):
    """
    Reads a text file, picks a non-empty line from a shuffled order of its lines, and returns it.
    It handles potential file-not-found errors or empty files gracefully.
    Returns an empty string if the file cannot be read, is empty, or no valid lines are found.
    The salt gives each file its own shuffled order, see brekel_shuffle.py.
    """
    if not file_path:
        # This case now properly handles when "None" is selected for a file or when the file_path is deliberately empty.
        return ""

    current_working_directory = os.getcwd()
    attempted_absolute_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        # Improved error message for user guidance
        print(f"[Brekel Node Error] Random line file not found.")
        print(f"  Attempted path: '{attempted_absolute_path}'")
        print(f"  Please ensure the file exists at this path.")
        # If the node's `ComfyUI/custom_nodes/ComfyUI-Brekel/auto_prompt_generator` folder is missing/empty, it's better to log it once upon node creation rather than every time this function is called if the list is empty.
        return ""

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            print(f"[Brekel Node Warning] File at '{attempted_absolute_path}' is empty or contains only whitespace lines. Returning empty string.")
            return ""

        return lines[shuffled_index(seed_value, len(lines), salt)]
    except Exception as e:
        print(f"[Brekel Node Error] An error occurred while reading or processing file '{attempted_absolute_path}': {e}. Returning empty string.")
        return ""




# --- CUSTOM COMFYUI NODE CLASS ---
class BrekelAutoPromptGenerator:
    """
    Brekel Auto Prompt Generator

    This node generates prompts by combining user-defined prefixes, postfixes, and random lines from text files.
    It allows for dynamic selection of text files to pick random lines from, and supports static prompts as well.
    """

    CATEGORY = "Brekel"
    FUNCTION = "brekel_generate_prompt"
    RETURN_TYPES = ("STRING",)
    OUTPUT_NODE = False

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        # The function is now called directly without the 's.' prefix
        txt_file_options = get_txt_files()

        return {
            "required": {
                "prefix": ("STRING", {"multiline": False, "default": "", "tooltip": "Prefix to prepend at the start of the prompt, for example to add your Lora trigger word(s)."}),
                "random_line_file1": (txt_file_options, {"default": "subjects.txt", "tooltip": f"File to pick a random line from. File must be in the 'ComfyUI/custom_nodes/ComfyUI-Brekel/{SUBFOLDER_NAME}' subfolder. If 'None' is selected, no line will be picked from this file."}),
                "random_line_file2": (txt_file_options, {"default": "locations.txt", "tooltip": f"File to pick a random line from. File must be in the 'ComfyUI/custom_nodes/ComfyUI-Brekel/{SUBFOLDER_NAME}' subfolder. If 'None' is selected, no line will be picked from this file."}),
                "random_line_file3": (txt_file_options, {"default": "styles.txt", "tooltip": f"File to pick a random line from. File must be in the 'ComfyUI/custom_nodes/ComfyUI-Brekel/{SUBFOLDER_NAME}' subfolder. If 'None' is selected, no line will be picked from this file."}),
                "random_line_file4": (txt_file_options, {"default": "details.txt", "tooltip": f"File to pick a random line from. File must be in the 'ComfyUI/custom_nodes/ComfyUI-Brekel/{SUBFOLDER_NAME}' subfolder. If 'None' is selected, no line will be picked from this file."}),
                "random_line_file5": (txt_file_options, {"None": "details.txt", "tooltip": f"File to pick a random line from. File must be in the 'ComfyUI/custom_nodes/ComfyUI-Brekel/{SUBFOLDER_NAME}' subfolder. If 'None' is selected, no line will be picked from this file."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFF, "step": 1, "forceInput": False, "control_after_generate": True, "tooltip": "Picks the lines. Set the control to 'increment' to get every line once, in shuffled order, before any line repeats. 'randomize' can repeat a line soon after."}),
                "mode": (["Random Prompt", "Static Prompt"], {"default": "Random Prompt", "tooltip": "Generate a random prompt or use the static"}),
                "static_prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "Static prompt to use when 'use_static_prompt' is set to 'true'. If empty, no static prompt will be used."}),
                "postfix": ("STRING", {"multiline": False, "default": "", "tooltip": "Postfix to append at the end of the prompt, for example to add your Lora trigger word(s)."}),
                "delimiter": ("STRING", {"default": ", ", "tooltip": "Delimiter to use between items. Use '\\n' for a newline character."}),
                "clean_whitespace": (["true", "false"], {"default": "true", "tooltip": "Remove leading and trailing whitespace from the final prompt"}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    def brekel_generate_prompt(self, prefix, mode, random_line_file1, random_line_file2, random_line_file3, random_line_file4, random_line_file5, seed, static_prompt, postfix, delimiter, clean_whitespace, unique_id=None):
        # Determine the effective delimiter (handle "\n" input as actual newline)
        effective_delimiter = delimiter
        if effective_delimiter == "\\n":
            effective_delimiter = "\n"

        core_content_derived = ""

        # Logic to determine the core content (random or static)
        if mode == "Random Prompt":
            script_dir = os.path.dirname(__file__)
            # Use the constant to build the path
            txt_files_dir = os.path.join(script_dir, SUBFOLDER_NAME)

            # Construct full paths only if a file is selected (not "None")
            file_path1 = os.path.join(txt_files_dir, random_line_file1) if random_line_file1 != "None" else ""
            file_path2 = os.path.join(txt_files_dir, random_line_file2) if random_line_file2 != "None" else ""
            file_path3 = os.path.join(txt_files_dir, random_line_file3) if random_line_file3 != "None" else ""
            file_path4 = os.path.join(txt_files_dir, random_line_file4) if random_line_file4 != "None" else ""
            file_path5 = os.path.join(txt_files_dir, random_line_file5) if random_line_file5 != "None" else ""

            random_phrases = []

            # Only attempt to pick a line if a valid file path exists
            if file_path1: random_phrases.append(pick_random_line_from_file(file_path1, seed, f"1:{random_line_file1}"))
            if file_path2: random_phrases.append(pick_random_line_from_file(file_path2, seed, f"2:{random_line_file2}"))
            if file_path3: random_phrases.append(pick_random_line_from_file(file_path3, seed, f"3:{random_line_file3}"))
            if file_path4: random_phrases.append(pick_random_line_from_file(file_path4, seed, f"4:{random_line_file4}"))
            if file_path5: random_phrases.append(pick_random_line_from_file(file_path5, seed, f"5:{random_line_file5}"))

            # Join non-empty random phrases with the effective delimiter
            core_content_derived = effective_delimiter.join(filter(None, random_phrases))
        else:
            core_content_derived = static_prompt

        # Build the final concatenated string from prefix, core_content, and postfix
        final_prompt_parts = []

        if prefix:
            final_prompt_parts.append(prefix)

        if core_content_derived: # Only add core_content if it's not an empty string
            final_prompt_parts.append(core_content_derived)

        if postfix:
            final_prompt_parts.append(postfix)

        # Join all existing parts with the effective delimiter
        # filter(None, ...) handles cases where parts like prefix/core_content/postfix are empty strings, ensuring no unwanted leading/trailing delimiters.
        concatenated_string = effective_delimiter.join(filter(None, final_prompt_parts))

        if clean_whitespace == "true":
            concatenated_string = concatenated_string.strip()

        # Send the prompt content to the UI
        if unique_id and PromptServer.instance:
            text_to_display = f"""<div style="margin-bottom: 4px; font-size: 0.8em; color: #888;">Prompt: {concatenated_string}</div>"""
            PromptServer.instance.send_progress_text(concatenated_string, unique_id)

        # Output must be a tuple, even for a single output
        return (concatenated_string,)




# --- ComfyUI Node Registration ---
NODE_CLASS_MAPPINGS = { "BrekelAutoPromptGenerator": BrekelAutoPromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = { "BrekelAutoPromptGenerator": "Brekel Auto Prompt Generator"}