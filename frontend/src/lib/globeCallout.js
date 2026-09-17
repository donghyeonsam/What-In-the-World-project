const EDGE = 16;
const GAP = 32;
const SWITCH_MARGIN = 28;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

// Keep the current side until it is nearly full; require extra room before switching back.
export function resolveGlobeCalloutSide({ x, width, stageWidth, preferRight, currentSide }) {
  const rightRoom = stageWidth - x - GAP - EDGE;
  const leftRoom = x - GAP - EDGE;
  const preferred = preferRight ? 'right' : 'left';
  const other = preferRight ? 'left' : 'right';
  const room = (side) => side === 'right' ? rightRoom : leftRoom;

  if (!currentSide) {
    if (room(preferred) >= width) return preferred;
    if (room(other) >= width) return other;
    return 'vertical';
  }
  if (currentSide === 'vertical') {
    if (room(preferred) >= width + SWITCH_MARGIN) return preferred;
    if (room(other) >= width + SWITCH_MARGIN) return other;
    return 'vertical';
  }
  if (room(currentSide) >= width + 12) return currentSide;
  const opposite = currentSide === 'right' ? 'left' : 'right';
  if (room(opposite) >= width + SWITCH_MARGIN) return opposite;
  return room(currentSide) >= width ? currentSide : 'vertical';
}

// Place a country callout beside its projected position, switching sides near the viewport edge.
export function layoutGlobeCallout({ x, y, width, height, stageWidth, stageHeight, preferRight, latitude, side, verticalBelow }) {
  const chosenSide = side || resolveGlobeCalloutSide({ x, width, stageWidth, preferRight });
  if (chosenSide !== 'vertical') {
    const right = chosenSide === 'right';
    const cardX = right ? x + GAP : x - GAP - width;
    const cardY = clamp(y - height * (latitude >= 45 ? 0.72 : 0.32), EDGE, stageHeight - height - EDGE);
    return {
      cardX,
      cardY,
      lineX: right ? cardX : cardX + width,
      lineY: clamp(y, cardY + 18, cardY + height - 18),
    };
  }

  // On a narrow stage, put the card above or below the country rather than clipping it.
  const cardX = clamp(x - width / 2, EDGE, stageWidth - width - EDGE);
  const below = verticalBelow ?? stageHeight - y >= y;
  const cardY = clamp(below ? y + GAP : y - height - GAP, EDGE, stageHeight - height - EDGE);
  return {
    cardX,
    cardY,
    lineX: clamp(x, cardX + 18, cardX + width - 18),
    lineY: cardY >= y ? cardY : cardY + height,
  };
}
