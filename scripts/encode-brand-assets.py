"""Encode lossless originals and appropriately sized high-DPI brand derivatives."""

from pathlib import Path

from PIL import Image


def main():
    asset_dir = Path(__file__).resolve().parent.parent / "public" / "assets"
    for stem in ("brand-mark-navy", "brand-lockup-navy"):
        source = asset_dir / f"{stem}.png"
        target = asset_dir / f"{stem}.lossless.webp"
        with Image.open(source) as original:
            pixels = original.convert("RGBA")
            pixels.save(target, "WEBP", lossless=True, exact=True, method=6)
            with Image.open(target) as encoded:
                if encoded.size != pixels.size or encoded.convert("RGBA").tobytes() != pixels.tobytes():
                    raise RuntimeError(f"Lossless verification failed: {target.name}")
        print(f"{source.name}: {source.stat().st_size} -> {target.stat().st_size} bytes; RGBA identical")
        if stem == "brand-mark-navy":
            for size in (192, 384):
                derivative = pixels.resize((size, size), Image.Resampling.LANCZOS)
                variant = asset_dir / f"{stem}-{size}.webp"
                derivative.save(variant, "WEBP", lossless=True, exact=True, method=6)
                with Image.open(variant) as encoded:
                    if encoded.convert("RGBA").tobytes() != derivative.tobytes():
                        raise RuntimeError(f"Lossless verification failed: {variant.name}")
                print(f"{variant.name}: {variant.stat().st_size} bytes; lossless high-DPI derivative")


if __name__ == "__main__":
    main()
