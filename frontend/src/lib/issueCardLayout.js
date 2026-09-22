// Stable edge slots keep the ranking readable while the globe rotates underneath.
export function issueCardSlots({ width, height, cardWidth, cardHeight, satelliteBottom = 0 }) {
  const bottom = height - 115;
  const columns = [110, Math.max(110, satelliteBottom + 12)].map((top, side) => {
    const count = Math.min(4, Math.max(0, Math.floor((bottom - top + 12) / (cardHeight + 12))));
    return Array.from({ length: count }, (_, index) => {
      const inset = 12 + Math.sin((index + 1) / (count + 1) * Math.PI) * Math.max(0, Math.min(26, (width - 2 * cardWidth - 36) / 2));
      return { x: side ? width - cardWidth - inset : inset, y: top + index * (cardHeight + 12) };
    });
  });
  return Array.from({ length: 4 }, (_, index) => [columns[0][index], columns[1][index]]).flat().filter(Boolean);
}

const overlaps = (a, b) => a.x < b.x + b.width + 10 && a.x + a.width + 10 > b.x
  && a.y < b.y + b.height + 10 && a.y + a.height + 10 > b.y;

export function placeIssueCards({ rows, slots, selectedId, width, height, cardWidth, cardHeight, obstacles = [] }) {
  const selected = rows.find((row) => row.id === selectedId);
  const visible = rows.slice(0, slots.length);
  // Selection changes inclusion only, never the ranking of already visible cards.
  if (selected && visible.length && !visible.includes(selected)) visible[visible.length - 1] = selected;
  const available = [...slots];
  const distance = (slot, row) => (slot.x + cardWidth / 2 - row.x) ** 2 + (slot.y + cardHeight / 2 - row.y) ** 2;
  const placed = visible.map((row) => {
    const nearest = available.reduce((best, slot, index) => distance(slot, row) < distance(available[best], row) ? index : best, 0);
    return { ...row, ...available.splice(nearest, 1)[0], width: cardWidth, height: cardHeight };
  });
  // Start from guaranteed non-overlapping edge slots, then bring front-side cards closer.
  placed.forEach((card, index) => {
    const anchor = visible[index];
    if (anchor.back) return;
    const candidates = [
      { x: anchor.x - cardWidth / 2, y: anchor.y - cardHeight - 12 },
      { x: anchor.x + 16, y: anchor.y - cardHeight / 2 },
      { x: anchor.x - cardWidth - 16, y: anchor.y - cardHeight / 2 },
      { x: anchor.x - cardWidth / 2, y: anchor.y + 12 },
    ].map((point) => ({ x: Math.max(12, Math.min(width - cardWidth - 12, point.x)),
      y: Math.max(110, Math.min(height - 115 - cardHeight, point.y)), width: cardWidth, height: cardHeight }));
    candidates.sort((a, b) => distance(a, anchor) - distance(b, anchor));
    const next = candidates.find((candidate) => distance(candidate, anchor) < distance(card, anchor)
      && !obstacles.some((obstacle) => overlaps(candidate, obstacle))
      && !placed.some((other, otherIndex) => otherIndex !== index && overlaps(candidate, other)));
    if (next) Object.assign(card, next);
  });
  return placed;
}
