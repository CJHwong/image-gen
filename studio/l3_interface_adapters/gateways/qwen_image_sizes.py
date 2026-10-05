"""The sizes the Qwen-Image-2.1 family was trained around.

Both backends that drive this model offer these, because it is one model: the
grid belongs to it, not to whichever adapter reaches it. A copy per backend
would drift, and one backend is not allowed to import another, so it sits here
beside the other shared helpers.

Every shape offers the same four tiers: about 0.25, 0.6 and 1 MP, then the large
size the list started with. Each keeps its exact ratio on a 16-pixel grid. The
model trains around 1 MP, so that tier is the default for a shape.
"""

SIZES = (
    ("1024 x 1024", 1024, 1024),
    ("512 x 512", 512, 512),
    ("768 x 768", 768, 768),
    ("1328 x 1328", 1328, 1328),
    ("768 x 432 (16:9)", 768, 432),
    ("1024 x 576 (16:9)", 1024, 576),
    ("1280 x 720 (16:9)", 1280, 720),
    ("1664 x 928 (16:9)", 1664, 928),
    ("432 x 768 (9:16)", 432, 768),
    ("576 x 1024 (9:16)", 576, 1024),
    ("720 x 1280 (9:16)", 720, 1280),
    ("928 x 1664 (9:16)", 928, 1664),
    ("576 x 432 (4:3)", 576, 432),
    ("896 x 672 (4:3)", 896, 672),
    ("1152 x 864 (4:3)", 1152, 864),
    ("1472 x 1104 (4:3)", 1472, 1104),
    ("432 x 576 (3:4)", 432, 576),
    ("672 x 896 (3:4)", 672, 896),
    ("864 x 1152 (3:4)", 864, 1152),
    ("1104 x 1472 (3:4)", 1104, 1472),
    # 3:2 and 2:3 were missing until the prompt rewriters arrived. Measured
    # 2026-09-27: three of four rewrites asked for 3:2, and the page could not
    # render it. Both ratios divide exactly on the 16 pixel grid, which is why
    # 1152x768 is 3:2 to the pixel rather than to within one percent.
    ("768 x 512 (3:2)", 768, 512),
    ("960 x 640 (3:2)", 960, 640),
    ("1152 x 768 (3:2)", 1152, 768),
    ("1536 x 1024 (3:2)", 1536, 1024),
    ("512 x 768 (2:3)", 512, 768),
    ("640 x 960 (2:3)", 640, 960),
    ("768 x 1152 (2:3)", 768, 1152),
    ("1024 x 1536 (2:3)", 1024, 1536),
)

# The edit engine treats output_resolution as an area budget, not a side: it
# derives width and height from the area and the last reference's ratio. So the
# shape always follows the reference, and this number only sets how many pixels.
# Every value here is a multiple of 32, which mflux validates before the model
# loads, and a 1280x720 reference then comes back 1280x704.
EDIT_RESOLUTIONS = (1024, 768, 512, 1344)

# An edit usually wants its input back at the size it came in at, so "match"
# is the default. The cap is there because the output size drives the whole
# denoising cost: a 2560x1440 screenshot would ask for about 1920, which is far
# past anything this machine renders in reasonable time. It is a multiple of 32
# for the same reason the list above is: the adapter takes the smaller of the two,
# so a cap off the grid would pass a number mflux rejects.
EDIT_MATCH_CAP = 1344
