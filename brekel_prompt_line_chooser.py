#
# Brekel Prompt Line Chooser Node for ComfyUI
# Version: 1.0.0
#
# Author: Brekel - https://brekel.com
#
# This node reads a text file that holds one prompt per line and outputs a single line.
# The line is picked by index, and because the index is a number widget it gets the
# "fixed / increment / decrement / randomize" control, so a batch of queued runs can
# step through or randomly pick the prompts in the file.


# --- CONFIGURATION CONSTANT ---
# Define the subfolder name where the example prompt list is stored.
SUBFOLDER_NAME = "prompt_line_chooser"


import os
import logging

# import block to communicate with the frontend
try:
    from server import PromptServer
except ImportError:
    # If the server is not available (e.g., in a headless environment) create a dummy class to prevent errors.
    class PromptServer:
        instance = None


# --- Setup basic logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Default File Path ---
SCRIPT_DIR = os.path.dirname(__file__)
DEFAULT_PROMPTS_FILE = os.path.join(SCRIPT_DIR, SUBFOLDER_NAME, "prompts.txt")


def _read_lines(file_path: str, skip_blank_lines: bool, skip_comment_lines: bool):
    """Read the file and return the list of usable prompt lines."""
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.read().splitlines()]

    if skip_blank_lines:
        lines = [line for line in lines if line != ""]
    if skip_comment_lines:
        lines = [line for line in lines if not line.startswith("#")]

    return lines


# --- PROMPT LINE CHOOSER CLASS ---
class BrekelPromptLineChooser:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "file_path": ("STRING", {
                    "default": DEFAULT_PROMPTS_FILE,
                    "multiline": False,
                    "placeholder": "C:/path/to/my/prompts.txt",
                    "tooltip": "Path to a .txt file containing one prompt per line."
                }),
                # control_after_generate adds the (fixed / increment / decrement /
                # randomize) box to this INT widget, so queued runs can step through
                # or randomly pick lines in the file.
                "line_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFFFFFFFFF,
                    "step": 1,
                    "control_after_generate": True,
                    "tooltip": "Which line to output, wraps around when it is larger than the number of lines."
                }),
                "skip_blank_lines": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Ignore empty lines so they do not take up an index."
                }),
                "skip_comment_lines": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Ignore lines starting with '#' so the file can hold comments."
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    # --- Node configuration for ComfyUI ---
    CATEGORY = "Brekel"
    FUNCTION = "choose_line"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)

    @classmethod
    def IS_CHANGED(s, file_path, line_index, skip_blank_lines, skip_comment_lines, unique_id=None):
        # Include the file's modification time so editing the prompt list re-runs the node
        # even when none of the widget values changed.
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            mtime = 0
        return (file_path, mtime, line_index, skip_blank_lines, skip_comment_lines)

    def choose_line(self, file_path: str, line_index: int, skip_blank_lines: bool, skip_comment_lines: bool, unique_id=None):
        """
        Main execution function. It reads the given text file and returns a single line,
        selected by index (wrapping around when the index exceeds the number of lines).
        """
        file_path = file_path.strip()

        if file_path == "":
            file_path = DEFAULT_PROMPTS_FILE
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        if not os.path.isfile(file_path):
            error_msg = f"Prompt file not found at '{file_path}'"
            logger.error(f"[Brekel Prompt Line Chooser] {error_msg}")
            return (f"ERROR: {error_msg}",)

        try:
            lines = _read_lines(file_path, skip_blank_lines, skip_comment_lines)
        except Exception as e:
            error_msg = f"Failed to read file '{file_path}': {e}"
            logger.error(f"[Brekel Prompt Line Chooser] {error_msg}")
            return (f"ERROR: {error_msg}",)

        if not lines:
            error_msg = f"No usable prompt lines found in '{file_path}'"
            logger.error(f"[Brekel Prompt Line Chooser] {error_msg}")
            return (f"ERROR: {error_msg}",)

        # Calculate index using modulo so it loops if index > line count
        actual_index = line_index % len(lines)
        chosen_line = lines[actual_index]

        print(f"[Brekel Prompt Line Chooser] index {line_index} -> line {actual_index + 1} of {len(lines)} in '{file_path}'")

        # Send the chosen line to the UI so it stays readable at the bottom of the node
        if unique_id and PromptServer.instance:
            text_to_display = f"Line {actual_index + 1}/{len(lines)}: {chosen_line}"
            PromptServer.instance.send_progress_text(text_to_display, unique_id)

        return (chosen_line,)


# --- ComfyUI Node Registration ---
NODE_CLASS_MAPPINGS = {"BrekelPromptLineChooser": BrekelPromptLineChooser,}
NODE_DISPLAY_NAME_MAPPINGS = {"BrekelPromptLineChooser": "Brekel Prompt Line Chooser",}
