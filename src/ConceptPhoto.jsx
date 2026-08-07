export default function ConceptPhoto({
  className = '',
  src,
  srcSet,
  sizes,
  mobileSrcSet,
  mobileSizes = '100vw',
  width,
  height,
  loading = 'lazy',
}) {
  return (
    <figure className={`concept-photo ${className}`.trim()} aria-hidden="true">
      <picture>
        {mobileSrcSet ? (
          <source media="(max-width: 767px)" srcSet={mobileSrcSet} sizes={mobileSizes} />
        ) : null}
        <img
          src={src}
          srcSet={srcSet}
          sizes={sizes}
          width={width}
          height={height}
          alt=""
          loading={loading}
          decoding="async"
        />
      </picture>
    </figure>
  )
}
