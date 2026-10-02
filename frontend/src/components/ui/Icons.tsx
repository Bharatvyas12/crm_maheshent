import type { NavIcon } from '@/lib/nav';

const PATHS: Record<NavIcon, string> = {
  home: 'M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5',
  clock: 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z',
  coffee: 'M4 8h13v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8Zm13 2h2a2 2 0 1 1 0 4h-2M4 21h13',
  'check-square': 'M9 11.5 11.5 14 16 9M4 5h16v14H4z',
  package: 'M12 3 3 7.5v9L12 21l9-4.5v-9L12 3Zm0 0v18M3 7.5l9 4.5 9-4.5',
  calendar: 'M4 6h16v14H4zM8 3v4M16 3v4M4 10h16',
  message: 'M4 5h16v10H8l-4 4V5Z',
  wallet: 'M3 7h16a2 2 0 0 1 2 2v8H3V7Zm0 0V6a1 1 0 0 1 1-1h13M16 13h1',
  bell: 'M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6Zm4 9a2 2 0 0 0 4 0',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0',
  users: 'M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0M17 11a3 3 0 1 0 0-6M21 20a5 5 0 0 0-4-4.9',
  shield: 'M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z',
  'map-pin': 'M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11Zm0-8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  gift: 'M4 11h16v10H4zM2 7h20v4H2zM12 7v14M12 7C10 7 8 5 8 4s2-2 4 3c2-5 4-4 4-3s-2 3-4 3Z',
  trending: 'M3 17l6-6 4 4 8-8M21 7v6h-6',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-3-2 1 .5 2-2 2-2-.5-1 2h-3l-1-2-2 .5-2-2 .5-2-2-1v-3l2-1-.5-2 2-2 2 .5 1-2h3l1 2 2-.5 2 2-.5 2 2 1v3Z',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  'file-text': 'M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6'
};

export function Icon({ name, className = 'h-5 w-5' }: { name: NavIcon; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}