# Типографика, controls и motion quality floor

Status: resolved

Исправить микротекст, hit areas, reduced-motion Canvas, offscreen/hidden-tab animation и загрузку тяжёлых логотипов.

## Comments

- Исходный runtime-аудит: 17 предупреждений о микротексте и 1 о tight leading.

## Answer

- Микротекст поднят до 11 px, основные CTA получили высоту не менее 44 px.
- Кириллические Manrope Variable и IBM Plex Mono проверены в production build.
- Canvas останавливает цикл вне viewport, в скрытой вкладке и при reduced-motion.
