#
# Brekel Load Image Node for ComfyUI
# Version: 1.0.0
#
# Author: Brekel - https://brekel.com
#
# This node is the same as the standard Load Image node except it adds the image name (without extension) as an output
# so it can for example be passed to the filename_prefix of an output node or used elsewhere in your workflow

import os
import torch
import numpy as np
import hashlib
from PIL import Image, ImageSequence, ImageOps

import folder_paths
import node_helpers

class BrekelLoadImage:
    
    # Returns IMAGE, MASK, and STRING (filename)
    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    
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

        # Return the base_name (without extension) as the third output
        return (output_image, output_mask, base_name)

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


# ComfyUI mappings (These need to be at the end of the file)
NODE_CLASS_MAPPINGS = {
    "BrekelLoadImage": BrekelLoadImage
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BrekelLoadImage": "Brekel Load Image (with Filename)"
}