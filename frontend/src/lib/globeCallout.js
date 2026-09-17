const EDGE = 16;
const GAP = 32;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

// Place a country callout beside its projected position, switching sides near the viewport edge.
export function layoutGlobeCallout({ x, y, width, height, stageWidth, stageHeight, preferRight, latitude }) {
  const rightRoom = stageWidth - x - GAP - EDGE;
  const leftRoom = x - GAP - EDGE;
  if (rightRoom >= width || leftRoom >= width) {
    const right = preferRight ? rightRoom >= width : leftRoom < width;
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
  const below = stageHeight - y >= y;
  const cardY = clamp(below ? y + GAP : y - height - GAP, EDGE, stageHeight - height - EDGE);
  return {
    cardX,
    cardY,
    lineX: clamp(x, cardX + 18, cardX + width - 18),
    lineY: cardY >= y ? cardY : cardY + height,
  };
}
