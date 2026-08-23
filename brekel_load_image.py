#
# Brekel Load Image Node for ComfyUI
# Version: 1.0.0
#
# Author: Brekel - https://brekel.com
#
# This node is the same as the standard Load Image node except it adds two extra outputs:
# - filename: the image name without extension, so it can for example be passed to the filename_prefix
#   of an output node or used elsewhere in your workflow
# - caption: the text embedded in the image (as written by the Brekel Save Image node or by other tools),
#   empty when the image has none

import os
import torch
import numpy as np
import hashlib
from PIL import Image, ImageSequence, ImageOps

import folder_paths
import node_helpers

class BrekelLoadImage:
    
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "filename", "caption")
    
    FUNCTION = "load_image"
    CATEGORY = "image"
    
    @classmethod
    def INPUT_TYPES(s):
        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        files = folder_paths.filter_files_content_types(files, ["image"])
        return {"required":
                    {"image": (sorted(files), {"image_upload": True})},
                }

    def load_image(self, image):
        # 'image' variable holds the full filename string (e.g., "my_picture.jpg")
        # Strip the file extension (e.g., "my_picture.jpg" -> "my_picture")
        base_name, _ = os.path.splitext(image)
        
        image_path = folder_paths.get_annotated_filepath(image)

        img = node_helpers.pillow(Image.open, image_path)

        output_images = []
        output_masks = []
        w, h = None, None

        excluded_formats = ['MPO']

        for i in ImageSequence.Iterator(img):
            i = node_helpers.pillow(ImageOps.exif_transpose, i)

            if i.mode == 'I':
                i = i.point(lambda i: i * (1 / 255))
            image_tensor = i.convert("RGB") 

            if len(output_images) == 0:
                w = image_tensor.size[0]
                h = image_tensor.size[1]

            if image_tensor.size[0] != w or image_tensor.size[1] != h:
                continue

            image_tensor = np.array(image_tensor).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_tensor)[None,]
            
            if 'A' in i.getbands():
                mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                mask = 1. - torch.from_numpy(mask)
            elif i.mode == 'P' and 'transparency' in i.info:
                mask = np.array(i.convert('RGBA').getchannel('A')).astype(np.float32) / 255.0
                mask = 1. - torch.from_numpy(mask)
            else:
                mask = torch.zeros((64,64), dtype=torch.float32, device="cpu")
            
            output_images.append(image_tensor)
            output_masks.append(mask.unsqueeze(0))

        if len(output_images) > 1 and img.format not in excluded_formats:
            output_image = torch.cat(output_images, dim=0)
            output_mask = torch.cat(output_masks, dim=0)
        else:
            output_image = output_images[0]
            output_mask = output_masks[0]

        return (output_image, output_mask, base_name, extract_caption(img))

    @classmethod
    def IS_CHANGED(s, image):
        image_path = folder_paths.get_annotated_filepath(image)
        m = hashlib.sha256()
        with open(image_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(s, image):
        if not folder_paths.exists_annotated_filepath(image):
            return "Invalid image file: {}".format(image)

        return True


# PNG text chunks and EXIF tags that can hold a caption
CAPTION_TEXT_KEYS = ("parameters", "Description", "caption")
EXIF_IMAGE_DESCRIPTION = 0x010E
EXIF_IFD = 0x8769
EXIF_USER_COMMENT = 0x9286


def extract_caption(img):
    """Read the caption embedded in an image, returns an empty string when there is none.

    Reads the PNG text chunks and the JPG/WEBP EXIF fields written by the Brekel Save Image node,
    which are the same ones used by most other tools. The workflow/prompt metadata of a regular
    ComfyUI image is deliberately ignored, that is not a caption.
    """
    text = getattr(img, "text", None) or {}
    for key in CAPTION_TEXT_KEYS:
        value = text.get(key)
        if isinstance(value, str) and value.strip():
            return value

    try:
        exif = img.getexif()
    except Exception:
        return ""

    # UserComment holds the full unicode text, ImageDescription is limited to ASCII
    comment = decode_user_comment(exif.get_ifd(EXIF_IFD).get(EXIF_USER_COMMENT))
    if comment:
        return comment

    description = exif.get(EXIF_IMAGE_DESCRIPTION)
    if isinstance(description, str) and description.strip() and not description.startswith(("workflow:", "prompt:")):
        return description

    return ""


def decode_user_comment(value):
    """Decode the EXIF UserComment field, which is prefixed by an 8 byte character code."""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, bytes):
        return ""

    prefix, payload = value[:8], value[8:]
    try:
        if prefix == b"UNICODE\x00":
            return payload.decode("utf-16-le").rstrip("\x00").strip()
        if prefix == b"ASCII\x00\x00\x00":
            return payload.decode("ascii", "ignore").rstrip("\x00").strip()
        return value.decode("utf-8", "ignore").rstrip("\x00").strip()
    except Exception:
        return ""


# ComfyUI mappings (These need to be at the end of the file)
NODE_CLASS_MAPPINGS = {
    "BrekelLoadImage": BrekelLoadImage
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BrekelLoadImage": "Brekel Load Image (with Filename & Caption)"
}