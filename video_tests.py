import math, os
import cairo

W, H = 1280, 720
FPS = 60
DURATION = 4
N = FPS * DURATION

out_dir = "frames_cairo"
os.makedirs(out_dir, exist_ok=True)

def ease_in_out(t: float) -> float:
    return 3*t*t - 2*t*t*t

for i in range(N):
    t = i / (N-1)
    e = ease_in_out(t)

    # create surface (ARGB32 with alpha)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surface)

    # background
    ctx.set_source_rgb(0.06, 0.07, 0.09)
    ctx.paint()

    # --- rectangle morphing into circle ---
    # Morph progress: 0 = rectangle, 1 = circle
    morph = e

    # Rectangle parameters
    rect_w0, rect_h0 = 320, 180
    rect_w1, rect_h1 = 200, 200  # for circle, width=height
    corner_radius0 = 20
    corner_radius1 = 100  # for circle, radius = half width

    # Interpolate width, height, and corner radius
    rect_w = rect_w0 + (rect_w1 - rect_w0) * morph
    rect_h = rect_h0 + (rect_h1 - rect_h0) * morph
    corner_radius = corner_radius0 + (corner_radius1 - corner_radius0) * morph

    # Center position
    cx, cy = W/2, H/2

    # Draw morphing rectangle/circle
    x0 = cx - rect_w/2
    y0 = cy - rect_h/2
    x1 = cx + rect_w/2
    y1 = cy + rect_h/2
    r = corner_radius

    # Draw rounded rectangle (becomes a circle as r approaches half width/height)
    ctx.set_source_rgba(0.2 + 0.5*morph, 0.7, 1.0-0.5*morph, 0.85)
    ctx.set_line_width(8)
    # Clamp radius to not exceed half width/height
    r = min(r, rect_w/2, rect_h/2)
    ctx.new_sub_path()
    ctx.arc(x1 - r, y0 + r, r, -math.pi/2, 0)
    ctx.arc(x1 - r, y1 - r, r, 0, math.pi/2)
    ctx.arc(x0 + r, y1 - r, r, math.pi/2, math.pi)
    ctx.arc(x0 + r, y0 + r, r, math.pi, 3*math.pi/2)
    ctx.close_path()
    ctx.fill_preserve()
    ctx.set_source_rgba(1,1,1,0.92)
    ctx.stroke()

    # --- fading in text: "Hello world" ---
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(60)
    text = "Hello world"
    xb, yb, tw, th, xa, ya = ctx.text_extents(text)
    tx, ty = W/2 - tw/2, H*0.78

    # Fade in: start after 20% of animation, finish at 60%
    fade_start = 0.2
    fade_end = 0.6
    if t < fade_start:
        fade = 0.0
    elif t > fade_end:
        fade = 1.0
    else:
        fade = (t - fade_start) / (fade_end - fade_start)
    ctx.set_source_rgba(1, 1, 1, fade)
    ctx.move_to(tx, ty)
    ctx.show_text(text)

    # save frame
    surface.write_to_png(f"{out_dir}/frame_{i:04d}.png")

print(f"Saved {N} frames in {out_dir}")
print("Make video with:")
print(f'ffmpeg -y -framerate {FPS} -i {out_dir}/frame_%04d.png -c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4')
