// Cisco-flavored node icons. Each is a single inline SVG component
// that uses `currentColor` for the silhouette — the parent decides the
// color via a Tailwind class (text-node-host, text-node-switch, …).
//
// A second `accent` color is exposed via the `text-accent` token for
// the small "lit" detail (screen, port lights) so the icon has the
// little punch of light Wireshark/Cisco icons always have.
//
// Sizes: 16 (compact) / 24 (canvas default) / 32 (project card).

import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & {
  /** Pixel size; defaults to 24. Most call sites use 14 / 22 / 28. */
  size?: number;
};

function withSize({ size = 24, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    xmlns: 'http://www.w3.org/2000/svg',
    'aria-hidden': true,
    ...rest,
  };
}

// ─── NodeHost ────────────────────────────────────────────────────────────
// A monitor on a stand — the universal "PC" glyph.
export function NodeHost(props: IconProps) {
  return (
    <svg {...withSize(props)}>
      {/* Monitor */}
      <rect
        x="2.5"
        y="3.5"
        width="19"
        height="13"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      {/* Screen (the lit detail) */}
      <rect x="4.5" y="5.5" width="15" height="9" rx="0.5" className="fill-accent" />
      {/* Stand */}
      <path
        d="M9 16.5 L8 20 L16 20 L15 16.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Base */}
      <line
        x1="6.5"
        y1="20"
        x2="17.5"
        y2="20"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ─── NodeSwitch ──────────────────────────────────────────────────────────
// A flat horizontal box with two arrows (the Cisco Catalyst iconography).
export function NodeSwitch(props: IconProps) {
  return (
    <svg {...withSize(props)}>
      {/* Body */}
      <rect
        x="2"
        y="8"
        width="20"
        height="8"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        fill="none"
      />
      {/* Left arrow (data in) */}
      <path
        d="M6 12 L4 12 M6 12 L4.75 10.75 M6 12 L4.75 13.25"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Right arrow (data out) */}
      <path
        d="M18 12 L20 12 M18 12 L19.25 10.75 M18 12 L19.25 13.25"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Lit port dots */}
      <circle cx="8" cy="12" r="0.9" className="fill-accent" />
      <circle cx="12" cy="12" r="0.9" className="fill-accent" />
      <circle cx="16" cy="12" r="0.9" className="fill-accent" />
    </svg>
  );
}

// ─── NodeRouter ──────────────────────────────────────────────────────────
// The classic Cisco cylinder. Routers "look round" in Cisco iconography.
export function NodeRouter(props: IconProps) {
  return (
    <svg {...withSize(props)}>
      {/* Top ellipse */}
      <ellipse
        cx="12"
        cy="5.5"
        rx="7"
        ry="2"
        stroke="currentColor"
        strokeWidth="1.5"
        fill="none"
      />
      {/* Sides */}
      <path
        d="M5 5.5 L5 18.5 C5 19.6 8.13 20.5 12 20.5 C15.87 20.5 19 19.6 19 18.5 L19 5.5"
        stroke="currentColor"
        strokeWidth="1.5"
        fill="none"
      />
      {/* Internal separator lines (the "rings" of a router cylinder) */}
      <path
        d="M5 9.5 C5 10.6 8.13 11.5 12 11.5 C15.87 11.5 19 10.6 19 9.5"
        stroke="currentColor"
        strokeWidth="1.2"
        opacity="0.5"
        fill="none"
      />
      <path
        d="M5 13.5 C5 14.6 8.13 15.5 12 15.5 C15.87 15.5 19 14.6 19 13.5"
        stroke="currentColor"
        strokeWidth="1.2"
        opacity="0.5"
        fill="none"
      />
      {/* Lit port (top, accent) */}
      <circle cx="12" cy="5.5" r="1" className="fill-accent" />
    </svg>
  );
}

// ─── NodeServer ──────────────────────────────────────────────────────────
// A tall rack with horizontal drive slots.
export function NodeServer(props: IconProps) {
  return (
    <svg {...withSize(props)}>
      {/* Frame */}
      <rect
        x="4"
        y="3"
        width="16"
        height="18"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        fill="none"
      />
      {/* Drive slots */}
      {[0, 1, 2].map((row) => (
        <g key={row}>
          <line
            x1="4.75"
            y1={6.5 + row * 4}
            x2="19.25"
            y2={6.5 + row * 4}
            stroke="currentColor"
            strokeWidth="1"
            opacity="0.5"
          />
          {/* slot line — drives */}
          <line
            x1="4.75"
            y1={6.5 + row * 4}
            x2="19.25"
            y2={6.5 + row * 4}
            stroke="currentColor"
            strokeWidth="1"
            opacity="0"
          />
        </g>
      ))}
      {/* LEDs (one per slot, lit accent) */}
      <circle cx="6.5" cy="6.5" r="0.8" className="fill-accent" />
      <circle cx="6.5" cy="10.5" r="0.8" className="fill-accent" />
      <circle cx="6.5" cy="14.5" r="0.8" className="fill-accent" />
      <circle cx="6.5" cy="18" r="0.8" className="fill-accent" />
    </svg>
  );
}

// ─── NodeAttacker ────────────────────────────────────────────────────────
// A hooded figure with glowing eyes — the threat actor silhouette.
export function NodeAttacker(props: IconProps) {
  return (
    <svg {...withSize(props)}>
      {/* Hood (the silhouette) */}
      <path
        d="M4 21 C4 13.5 7.5 8 12 8 C16.5 8 20 13.5 20 21 L4 21 Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Face shadow (deeper) */}
      <path
        d="M7.5 19 C7.5 14.5 9.5 11 12 11 C14.5 11 16.5 14.5 16.5 19 L7.5 19 Z"
        fill="currentColor"
        opacity="0.25"
      />
      {/* Eyes (the menace) */}
      <ellipse cx="9.75" cy="15.5" rx="0.9" ry="1.3" className="fill-accent" />
      <ellipse cx="14.25" cy="15.5" rx="0.9" ry="1.3" className="fill-accent" />
      {/* Shoulders line */}
      <line
        x1="2.5"
        y1="21"
        x2="21.5"
        y2="21"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ─── IconResolver — single entry point by kind ───────────────────────────

import type { NodeKind } from '../../types';

interface NodeIconProps extends IconProps {
  kind: NodeKind;
}

const KIND_TO_ICON = {
  host: NodeHost,
  switch: NodeSwitch,
  router: NodeRouter,
  server: NodeServer,
  attacker: NodeAttacker,
} as const;

export function NodeIcon({ kind, ...rest }: NodeIconProps) {
  const Comp = KIND_TO_ICON[kind];
  return <Comp {...rest} />;
}
