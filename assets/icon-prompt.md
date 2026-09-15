# App icon — v0.2

Created with the built-in `image_gen` tool. The artwork uses an indigo rounded tile, two white screenshot segments, and a cyan cut line.

## Final assets

- `app-icon.png`: 1024 × 1024 RGBA PNG, with transparent surround.
- `app-icon.ico`: Windows icon containing 16, 24, 32, 48, 64, 128, and 256 pixel images.

Pillow was used only for Lanczos resizing and ICO format packaging. Alpha transparency was preserved. The 256 pixel ICO image was visually inspected.

## Generation prompt

```text
Use case: logo-brand
Asset type: finished Windows desktop application icon, square 1024 x 1024 PNG, genuinely transparent background outside the icon
Primary request: design an elegant minimal app icon for Long Screenshot Splitter, a tool that cuts tall screenshots into shorter images.
Subject: a bold rounded-square tile in a subtle indigo to violet-blue gradient. Centered on the tile is a simple white tall screenshot symbol split horizontally into two detached rectangular panels with a clear narrow gap. A crisp short cyan horizontal cut dash crosses the gap and extends slightly beyond the white panels on each side. Each panel contains only one or two bold short indigo rounded content bars, legible and restrained.
Composition/framing: a single centered icon, tile occupies 90 percent of the square canvas, roughly 5 percent fully transparent padding on all sides; symmetric front view; strong silhouette readable at 16, 24, 32, 48, 64, 128 and 256 pixels.
Style/medium: premium polished Windows utility icon, vector-like flat geometry, clean large forms, very subtle gradient depth only.
Color palette: indigo #4F46E5, deep blue-violet #4338CA, clean white #FFFFFF, tiny cyan accent #67E8F9.
Constraints: no text, no letters, no numbers, no watermark, no extra objects, no drop shadow outside the rounded tile, no decorative rays, no scissor details, no perspective, no frame around the canvas. The surrounding background MUST be actual alpha transparency, never a rendered checkerboard. Rounded tile corners are clean and generous.
```

## Edge refinement prompt

```text
Use case: precise-object-edit
Edit target: the provided icon.
Primary request: clean ONLY the outer silhouette and transparent surround. Remove all scattered blue speckles, wisps, halo remnants, and rough pixels OUTSIDE the single indigo rounded-square tile. Make the tile outline a perfectly clean smooth geometric rounded square. All pixels outside the tile except one antialiased boundary must be fully transparent.
Invariants: preserve exactly the existing composition, proportions, white top and bottom screenshot segments, four indigo content bars, cyan horizontal divider, indigo gradient, and canvas framing. Do not redesign anything inside the tile. No text, no additional elements, no shadows, no rendered checkerboard. Final image is RGBA PNG with genuine alpha transparency.
```

## Final transparency prompt

```text
Use case: background-extraction.
Make this exact icon have a TRUE TRANSPARENT background. Remove the gray checkerboard surrounding the indigo rounded square entirely, and replace it with real alpha transparency. Keep the complete icon itself unchanged. Return RGBA PNG with alpha=0 outside the icon, clean smooth antialiased edge, no speckles or halo. This is an image background removal request, not a request to draw transparency visualization. No gray checkerboard may exist in any actual opaque pixel. Preserve the indigo tile and all white/cyan inner graphic details exactly.
```
