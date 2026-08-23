#
# Brekel Save Image Node for ComfyUI
# Version: 1.0.0
#
# Author: Brekel - https://brekel.com
#
# Like the standard Save Image node, but with control over the file numbering and the embedded metadata.
#
# Key Features:
# - Save as PNG or JPG (with quality control).
# - A save toggle that turns the node into a preview node, leaving the output folder untouched.
# - start_number sets the first number used, so a sequence can start at any offset.
# - fill_gaps scans the output folder and re-uses missing numbers, so deleting image_00003 while
#   image_00004 exists makes the next save land on _00003 again, keeping the range continuous.
# - Numbering is shared between PNG and JPG so the two formats never claim the same number.
# - By default the workflow/prompt is embedded (drag & drop the PNG onto the canvas to restore it),
#   but connecting the optional caption input embeds that text instead.

import json
import os
import random
import re

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

import folder_paths
from comfy.cli_args import args

# EXIF tags used for the JPG metadata
EXIF_IMAGE_DESCRIPTION = 0x010E
EXIF_MAKE = 0x010F
EXIF_IFD = 0x8769
EXIF_USER_COMMENT = 0x9286

# A single EXIF APP1 segment cannot exceed 64KB, leave a little headroom
MAX_EXIF_BYTES = 60000

# Extensions taken into account when scanning for already used numbers
KNOWN_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


class BrekelSaveImage:

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The images to save."}),
                "save": ("BOOLEAN", {
                    "default": True,
                    "label_on": "save", "label_off": "preview only",
                    "tooltip": "Turn off to act like a Preview Image node, the images go to the temp folder and the output folder and its numbering are left untouched."
                }),
                "filename_prefix": ("STRING", {
                    "default": "ComfyUI",
                    "tooltip": "The prefix for the file to save. This may include formatting information such as %date:yyyy-MM-dd% or %Empty Latent Image.width% to include values from nodes."
                }),
                "file_format": (["png", "jpg"], {
                    "default": "png",
                    "tooltip": "PNG is lossless and can be dragged onto the canvas to restore the workflow, JPG is smaller but stores its metadata in EXIF."
                }),
                "quality": ("INT", {
                    "default": 95, "min": 1, "max": 100,
                    "tooltip": "JPG quality, ignored when saving PNG."
                }),
                "start_number": ("INT", {
                    "default": 1, "min": 0, "max": 99999,
                    "tooltip": "The first number of the sequence, numbers below this are never used."
                }),
                "fill_gaps": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Re-use missing numbers in the sequence on disk instead of always appending after the highest one."
                }),
            },
            "optional": {
                "caption": ("STRING", {
                    "forceInput": True,
                    "tooltip": "When connected this text is embedded into the image instead of the workflow/prompt."
                }),
            },
            "hidden": {
                "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "filename")
    FUNCTION = "save_images"

    OUTPUT_NODE = True

    CATEGORY = "image"
    DESCRIPTION = "Saves the input images as PNG or JPG with control over the numbering and the embedded metadata."

    def save_images(self, images, save=True, filename_prefix="ComfyUI", file_format="png", quality=95,
                    start_number=1, fill_gaps=True, caption=None, prompt=None, extra_pnginfo=None):

        if save:
            output_dir = self.output_dir
            output_type = self.type
            compress_level = self.compress_level
        else:
            # Preview only, a random suffix keeps the temp files of separate runs apart and
            # makes the numbering below start at 1 without ever touching the output folder
            output_dir = folder_paths.get_temp_directory()
            output_type = "temp"
            compress_level = 1
            filename_prefix += "_temp_" + "".join(random.choice("abcdefghijklmnopqrstupvxyz") for x in range(5))
            start_number = 1
            fill_gaps = True

        full_output_folder, filename, _, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, output_dir, images[0].shape[1], images[0].shape[0])

        # An empty string (an unconnected reroute, an empty prompt box) falls back to the workflow metadata
        if caption is not None and caption.strip() == "":
            caption = None

        extension = "jpg" if file_format == "jpg" else "png"

        # Numbers already on disk, per resolved base name (%batch_num% can make them differ within one batch)
        used_numbers = {}

        results = list()
        last_filename = ""

        for (batch_number, image) in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))

            if filename_with_batch_num not in used_numbers:
                used_numbers[filename_with_batch_num] = scan_used_numbers(full_output_folder, filename_with_batch_num)
            used = used_numbers[filename_with_batch_num]

            counter = next_number(used, start_number, fill_gaps)
            used.add(counter)

            file = f"{filename_with_batch_num}_{counter:05}_.{extension}"
            path = os.path.join(full_output_folder, file)

            if extension == "jpg":
                img = img.convert("RGB")
                exif_bytes = build_jpeg_exif(img, caption, prompt, extra_pnginfo)
                if exif_bytes is None:
                    img.save(path, quality=quality, subsampling=0, optimize=True)
                else:
                    img.save(path, quality=quality, subsampling=0, optimize=True, exif=exif_bytes)
            else:
                img.save(path, pnginfo=build_png_metadata(caption, prompt, extra_pnginfo),
                         compress_level=compress_level)

            results.append({
                "filename": file,
                "subfolder": subfolder,
                "type": output_type
            })
            last_filename = f"{filename_with_batch_num}_{counter:05}_"

        return {"ui": {"images": results}, "result": (images, last_filename)}


def scan_used_numbers(folder, base_name):
    """Collect the numbers already used by files named <base_name>_<number>_.<ext> in folder."""
    pattern = re.compile(re.escape(base_name) + r"_(\d+)_", re.IGNORECASE)
    used = set()
    try:
        entries = os.listdir(folder)
    except FileNotFoundError:
        os.makedirs(folder, exist_ok=True)
        return used

    for entry in entries:
        name, ext = os.path.splitext(entry)
        if ext.lower() not in KNOWN_EXTENSIONS:
            continue
        match = pattern.fullmatch(name)
        if match:
            used.add(int(match.group(1)))
    return used


def next_number(used, start_number, fill_gaps):
    """Pick the number to save as, either the first free one or the one after the highest used."""
    if fill_gaps:
        counter = start_number
        while counter in used:
            counter += 1
        return counter

    highest = max((n for n in used if n >= start_number), default=None)
    return start_number if highest is None else highest + 1


def build_png_metadata(caption, prompt, extra_pnginfo):
    """Embed the caption as text chunks, or the workflow/prompt like the standard Save Image node does."""
    if args.disable_metadata:
        return None

    metadata = PngInfo()
    if caption is not None:
        # "parameters" is what most external tools read, "Description" is the generic PNG equivalent
        metadata.add_text("parameters", caption)
        metadata.add_text("Description", caption)
        return metadata

    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt))
    if extra_pnginfo is not None:
        for x in extra_pnginfo:
            metadata.add_text(x, json.dumps(extra_pnginfo[x]))
    return metadata


def build_jpeg_exif(img, caption, prompt, extra_pnginfo):
    """Build the EXIF block for a JPG, returns None when there is nothing to embed.

    The workflow/prompt use the same "key:value" strings ComfyUI writes into WEBP files.
    JSON of a large workflow can outgrow the 64KB EXIF segment, in that case it is dropped
    rather than failing the save.
    """
    if args.disable_metadata:
        return None

    exif = img.getexif()

    if caption is not None:
        exif[EXIF_IMAGE_DESCRIPTION] = caption
        exif.get_ifd(EXIF_IFD)[EXIF_USER_COMMENT] = b"UNICODE\x00" + caption.encode("utf-16-le")
        return fit_exif(exif, [EXIF_USER_COMMENT], [EXIF_IMAGE_DESCRIPTION])

    if extra_pnginfo is not None and "workflow" in extra_pnginfo:
        exif[EXIF_IMAGE_DESCRIPTION] = "workflow:" + json.dumps(extra_pnginfo["workflow"])
    if prompt is not None:
        exif[EXIF_MAKE] = "prompt:" + json.dumps(prompt)

    if len(exif) == 0:
        return None

    # Drop the workflow first, it is the largest and the least useful of the two in a JPG
    return fit_exif(exif, [], [EXIF_IMAGE_DESCRIPTION, EXIF_MAKE])


def fit_exif(exif, sub_ifd_tags, tags):
    """Serialize the EXIF block, dropping tags in the given order until it fits into one APP1 segment."""
    while True:
        try:
            data = exif.tobytes()
            if len(data) <= MAX_EXIF_BYTES:
                return data
        except Exception as e:
            print(f"[Brekel Save Image] could not encode EXIF metadata: {e}")

        if sub_ifd_tags:
            exif.get_ifd(EXIF_IFD).pop(sub_ifd_tags.pop(0), None)
        elif tags:
            exif.pop(tags.pop(0), None)
        else:
            print("[Brekel Save Image] metadata too large for JPG EXIF, saved without it")
            return None


# ComfyUI mappings (These need to be at the end of the file)
NODE_CLASS_MAPPINGS = {
    "BrekelSaveImage": BrekelSaveImage
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BrekelSaveImage": "Brekel Save Image (PNG/JPG)"
}
