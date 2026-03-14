/**
 * Shared theme constants — single source of truth for editorial design tokens.
 *
 * Status badges, level badges, and chart colors all live here so that
 * 50+ component files can import instead of duplicating.
 */

/* ------------------------------------------------------------------ */
/*  Player pathway status badges (warm-editorial palette)              */
/* ------------------------------------------------------------------ */

export const STATUS_BADGE_CLASSES = {
  first_team: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  on_loan:    'bg-amber-50 text-amber-800 border-amber-200',
  academy:    'bg-orange-50 text-orange-800 border-orange-200',
  released:   'bg-stone-100 text-stone-700 border-stone-200',
  sold:       'bg-rose-50 text-rose-800 border-rose-200',
}

/* ------------------------------------------------------------------ */
/*  Academy level badges                                               */
/* ------------------------------------------------------------------ */

export const LEVEL_BADGE_CLASSES = {
  U18:     'bg-violet-50 text-violet-800 border-violet-200',
  U21:     'bg-emerald-50 text-emerald-800 border-emerald-200',
  U23:     'bg-purple-50 text-purple-800 border-purple-200',
  Reserve: 'bg-orange-50 text-orange-800 border-orange-200',
}

/* ------------------------------------------------------------------ */
/*  Chart per-stat colors (warm palette)                               */
/* ------------------------------------------------------------------ */

export const CHART_STAT_COLORS = {
  goals:        '#059669', // emerald-600
  assists:      '#d97706', // amber-600
  rating:       '#ca8a04', // yellow-600
  minutes:      '#78716c', // stone-500
  shots_total:  '#dc2626', // red-600
  shots_on:     '#db2777', // pink-600
  passes_total: '#7c3aed', // violet-600
  passes_key:   '#0d9488', // teal-600
  tackles_total:'#ea580c', // orange-600
  duels_won:    '#0891b2', // cyan-600
  saves:        '#65a30d', // lime-600
}

/* ------------------------------------------------------------------ */
/*  Chart position colors (radar chart)                                */
/* ------------------------------------------------------------------ */

export const CHART_POSITION_COLORS = {
  Forward:    '#dc2626', // red-600
  Midfielder: '#d97706', // amber-600
  Defender:   '#059669', // emerald-600
  Goalkeeper: '#ca8a04', // yellow-600
}

/* ------------------------------------------------------------------ */
/*  Constellation status colors (hex for canvas)                       */
/* ------------------------------------------------------------------ */

export const CONSTELLATION_STATUS_COLORS = {
  first_team: '#059669', // emerald-600
  on_loan:    '#d97706', // amber-600
  academy:    '#ea580c', // orange-600
  released:   '#78716c', // stone-500
  sold:       '#e11d48', // rose-600
}

/* ------------------------------------------------------------------ */
/*  Journey level colors (hex for dynamic styles)                      */
/* ------------------------------------------------------------------ */

export const JOURNEY_LEVEL_COLORS = {
  'U18':                '#7c3aed', // violet-600
  'U19':                '#8b5cf6', // violet-500
  'U21':                '#059669', // emerald-600
  'U23':                '#0891b2', // cyan-600
  'Reserve':            '#ea580c', // orange-600
  'First Team':         '#059669', // emerald-600
  'International':      '#d97706', // amber-600
  'International Youth':'#c026d3', // fuchsia-600
}

/* ------------------------------------------------------------------ */
/*  Chart infrastructure — use CSS var references where possible       */
/* ------------------------------------------------------------------ */

export const CHART_GRID_COLOR = '#e7e5e4'       // stone-200
export const CHART_AXIS_COLOR = '#78716c'        // stone-500
export const CHART_TOOLTIP_BG = '#ffffff'
export const CHART_TOOLTIP_BORDER = '#d6d3d1'    // stone-300
