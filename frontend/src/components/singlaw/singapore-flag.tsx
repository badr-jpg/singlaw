export function SingaporeFlag() {
  return (
    <svg className="singapore-flag" viewBox="0 0 90 60" role="img" aria-label="Singapore flag">
      <rect width="90" height="60" fill="#fff" />
      <path d="M0 0h90v30H0z" fill="#ef3340" />
      <circle cx="18" cy="15" r="10" fill="#fff" />
      <circle cx="22" cy="12.5" r="9" fill="#ef3340" />
      {[
        [41, 6],
        [49.56, 12.22],
        [46.29, 22.28],
        [35.71, 22.28],
        [32.44, 12.22],
      ].map(([x, y]) => (
        <polygon
          key={`${x}-${y}`}
          transform={`translate(${x} ${y})`}
          points="0,-3.2 .72,-1 3.04,-.99 1.16,.38 1.88,2.59 0,1.22 -1.88,2.59 -1.16,.38 -3.04,-.99 -.72,-1"
          fill="#fff"
        />
      ))}
    </svg>
  );
}
