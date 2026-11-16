import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import './index.css';

/* ============================================================================
 * CONFIG
 * ==========================================================================*/

const API_BASE = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws';
const CLIPS_ENDPOINT = `${API_BASE}/api/clips`;
const HUD_FRAME_URL = `${API_BASE}/media/HUD/${encodeURIComponent('Dados Hud.png')}`;
const VOICE_FRAME_URL = `${API_BASE}/media/HUD/Voice.jpg`;

const RECONNECT_DELAY_MS = 3000;
const CLIPS_RETRY_MS = 5000;
const SWAP_RELOAD_DELAY_MS = 100;
const PLAYBACK_WATCHDOG_MS = 2000;
const SHUFFLE_CLIPS = false; // true = orden aleatorio (sin repetir el mismo clip dos veces seguidas)

const MEDIA_DISPLAY_MS = 8000; // tiempo visible en pantalla
const MEDIA_EXIT_MS = 700; // debe coincidir con la duración de .ppt-out en index.css
const MEDIA_LOAD_TIMEOUT_MS = 10000; // descarta medios que no cargan
const MEDIA_MAX_QUEUE = 10;

/** Ancho del HUD en px (el alto lo define la proporción natural del PNG). */
const HUD_WIDTH = 420;
/** Zona de la pantalla negra del chasis, en % relativo a la imagen. Calibrado para Dados Hud.png 408×385 */
const HUD_SCREEN = { left: 19.4, top: 13.6, width: 36.7, height: 53.9 };
/** Posición del LED "STATUS" del chasis, en %. Calibrado para Dados Hud.png 408×385 */
const HUD_STATUS_LED = { left: 62.3, top: 20.1 };
/** Muesca de la perilla: máscara radial para dejar visible la perilla.
 * Aprox. 28 px (en el PNG) × HUD_WIDTH/408 + 1 px margen ≈ 30 px desde la esquina inferior izquierda. */
const HUD_SCREEN_NOTCH_PX = Math.round((28 * HUD_WIDTH) / 408 + 1);
const HUD_SCREEN_MASK = `radial-gradient(circle ${HUD_SCREEN_NOTCH_PX}px at 0 100%, transparent ${HUD_SCREEN_NOTCH_PX - 0.5}px, #000 ${HUD_SCREEN_NOTCH_PX}px)`;

/** Ancho del HUD de voz en px (el alto lo define la proporción natural del JPG). */
const VOICE_HUD_WIDTH = 240;                 // ≈ 240 × 469 px
/** Pantalla negra de Voice.jpg (736 × 1439), en %. Recalibrar si cambia el JPG. */
const VOICE_HUD_SCREEN = { left: 8.97, top: 25.5, width: 81.7, height: 56.0 };
const VOICE_STALE_MS = 15000;                // 3 latidos perdidos -> STANDBY
const VOICE_MAX_ROWS = 10;                   // filas visibles; el resto -> "+N MORE"
// U+FE0E = variante de texto: el símbolo toma el color LED en vez del emoji a color.
const VOICE_ICON_SILENT = '\u{1F508}︎'; // 🔈
const VOICE_ICON_SPEAKING = '\u{1F50A}︎·'; // 🔊·

const VIDEO_EXT = /\.(mp4|webm|mov|m4v|ogv)(\?.*)?$/i;
const PPT_ANIMS = ['fade', 'zoom', 'fly-left', 'fly-right', 'fly-top'] as const;

/* ============================================================================
 * TYPES
 * ==========================================================================*/

type DiceRollEvent = {
  type: 'DICE_ROLL';
  user: string;
  dice_count: number;
  successes: number;
};

type MediaKind = 'image' | 'video';

type NewMediaEvent = {
  type: 'NEW_MEDIA';
  url: string;
  user: string;
  /** Tipo real detectado por el backend (magic bytes). Opcional por compatibilidad. */
  media_type?: MediaKind;
};

type VoiceMember = { id: string; name: string; speaking: boolean };

type VoiceStateEvent = { type: 'VOICE_STATE'; channel: string | null; members: VoiceMember[] };

type OverlayEvent = DiceRollEvent | NewMediaEvent | VoiceStateEvent;
type SocketStatus = 'connecting' | 'open' | 'closed';
type PptAnim = (typeof PPT_ANIMS)[number];
type MediaPhase = 'loading' | 'in' | 'out';
type Slot = 0 | 1;

type MediaItem = {
  id: number;
  url: string;
  user: string;
  anim: PptAnim;
  isVideo: boolean;
};

/* ============================================================================
 * HELPERS
 * ==========================================================================*/

const clipUrl = (filename: string) =>
  `${API_BASE}/media/Gameplay/${encodeURIComponent(filename)}`;

function resolveMediaUrl(url: string): string {
  if (/^(https?:|data:|blob:)/i.test(url)) return url;
  return url.startsWith('/') ? `${API_BASE}${url}` : `${API_BASE}/${url}`;
}

function pickNextIndex(current: number, total: number): number {
  if (total <= 1) return 0;
  if (!SHUFFLE_CLIPS) return (current + 1) % total;
  let next = current;
  while (next === current) next = Math.floor(Math.random() * total);
  return next;
}

function toCount(value: unknown): number | null {
  const n = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN;
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : null;
}

function parseEvent(raw: unknown): OverlayEvent | null {
  if (typeof raw !== 'string') return null;
  let data: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    data = parsed as Record<string, unknown>;
  } catch {
    return null;
  }

  if (data.type === 'DICE_ROLL') {
    const dice = toCount(data.dice_count);
    const successes = toCount(data.successes);
    if (dice === null || successes === null) return null;
    return {
      type: 'DICE_ROLL',
      user: String(data.user ?? 'UNKNOWN'),
      dice_count: dice,
      successes,
    };
  }

  if (data.type === 'NEW_MEDIA' && typeof data.url === 'string' && data.url) {
    const mediaType =
      data.media_type === 'video' || data.media_type === 'image' ? data.media_type : undefined;
    return {
      type: 'NEW_MEDIA',
      url: data.url,
      user: String(data.user ?? 'UNKNOWN'),
      media_type: mediaType,
    };
  }

  if (data.type === 'VOICE_STATE') {
    const channel = data.channel;
    if (channel !== null && typeof channel !== 'string') return null;
    if (!Array.isArray(data.members)) return null;
    const members =
      channel === null
        ? []
        : (data.members as unknown[])
            .filter(
              (m): m is { id: unknown; name: unknown; speaking: unknown } =>
                !!m && typeof m === 'object' && !Array.isArray(m),
            )
            .filter((m): m is VoiceMember => {
              if (typeof m.id !== 'string') return false;
              if (typeof m.name !== 'string' || m.name.length === 0) return false;
              return typeof m.speaking === 'boolean';
            })
            // Recorta por code points (como el backend) para no partir un emoji.
            .map((m) => ({ id: m.id, name: Array.from(m.name).slice(0, 32).join(''), speaking: m.speaking }))
            .slice(0, 25);
    return { type: 'VOICE_STATE', channel, members };
  }

  return null;
}

/** Rellena con ceros a 2 dígitos ("7" -> "07"), estilo display de reloj. */
const padDigits = (n: number) => String(n).padStart(2, '0');

/* ============================================================================
 * HOOK: WebSocket resiliente (reconexión cada 3 s)
 * ==========================================================================*/

function useOverlaySocket(onEvent: (evt: OverlayEvent) => void): SocketStatus {
  const handlerRef = useRef(onEvent);
  const [status, setStatus] = useState<SocketStatus>('connecting');

  useEffect(() => {
    handlerRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus('connecting');
      ws = new WebSocket(WS_URL);

      ws.onopen = () => setStatus('open');
      ws.onmessage = (msg: MessageEvent) => {
        const evt = parseEvent(msg.data);
        if (evt) handlerRef.current(evt);
      };
      ws.onerror = () => ws?.close(); // onclose se encarga de reconectar
      ws.onclose = () => {
        setStatus('closed');
        if (!disposed) reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
      };
    };

    connect();

    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        ws.close();
      }
    };
  }, []);

  return status;
}

/* ============================================================================
 * HOOK: Cola de imágenes / GIFs (uno a la vez, nunca se pisan)
 * ==========================================================================*/

function useMediaQueue() {
  const queueRef = useRef<MediaItem[]>([]);
  const idRef = useRef(0);
  const [current, setCurrent] = useState<MediaItem | null>(null);
  const [phase, setPhase] = useState<MediaPhase>('loading');
  const [queueTick, setQueueTick] = useState(0);

  const enqueue = useCallback((url: string, user: string, mediaType?: MediaKind) => {
    const resolved = resolveMediaUrl(url);
    queueRef.current.push({
      id: ++idRef.current,
      url: resolved,
      user,
      anim: PPT_ANIMS[Math.floor(Math.random() * PPT_ANIMS.length)],
      isVideo: mediaType ? mediaType === 'video' : VIDEO_EXT.test(resolved),
    });
    if (queueRef.current.length > MEDIA_MAX_QUEUE) queueRef.current.shift();
    setQueueTick((t) => t + 1);
  }, []);

  // Saca el siguiente elemento cuando el escenario queda libre.
  useEffect(() => {
    if (current) return;
    const next = queueRef.current.shift();
    if (next) {
      setPhase('loading');
      setCurrent(next);
    }
  }, [current, queueTick]);

  // Máquina de estados: loading -> in (8 s) -> out (fade-out) -> desmontar.
  useEffect(() => {
    if (!current) return;
    let timer: number;
    if (phase === 'loading') {
      timer = window.setTimeout(() => setCurrent(null), MEDIA_LOAD_TIMEOUT_MS);
    } else if (phase === 'in') {
      timer = window.setTimeout(() => setPhase('out'), MEDIA_DISPLAY_MS);
    } else {
      timer = window.setTimeout(() => setCurrent(null), MEDIA_EXIT_MS);
    }
    return () => window.clearTimeout(timer);
  }, [current, phase]);

  const onReady = useCallback(() => setPhase((p) => (p === 'loading' ? 'in' : p)), []);
  const onFail = useCallback(() => setCurrent(null), []);

  return { current, phase, enqueue, onReady, onFail };
}

/* ============================================================================
 * COMPONENT: Gameplay loop
 * Doble buffer: mientras un <video> reproduce, el otro precarga el siguiente
 * clip. Al terminar, se hace swap instantáneo -> sin pantalla negra.
 * ==========================================================================*/

function GameplayLoop() {
  const [clips, setClips] = useState<string[]>([]);
  const [activeSlot, setActiveSlot] = useState<Slot>(0);

  const slotARef = useRef<HTMLVideoElement>(null);
  const slotBRef = useRef<HTMLVideoElement>(null);
  const clipsRef = useRef<string[]>([]);
  const activeSlotRef = useRef<Slot>(0);
  const slotClipIndex = useRef<[number, number]>([-1, -1]);
  // Evita avances concurrentes (onEnded + watchdog) mientras play() está pendiente.
  const advancingRef = useRef(false);

  const getSlot = (slot: Slot) => (slot === 0 ? slotARef.current : slotBRef.current);

  const loadInto = useCallback(
    (slot: Slot, index: number) => {
      const el = slot === 0 ? slotARef.current : slotBRef.current;
      const name = clipsRef.current[index];
      if (!el || !name) return;
      slotClipIndex.current[slot] = index;
      el.src = clipUrl(name);
      el.load();
      // Sin autoplay por atributo; se arranca explícitamente si es el activo.
      if (slot === activeSlotRef.current) {
        el.play().catch(() => undefined);
      }
    },
    // Eliminamos activeSlot de dependencias para evitar ciclos; usamos activeSlotRef para la lógica.
    []
  );

  // Fetch de la lista de clips (reintenta si el backend aún no está arriba).
  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;
    const controller = new AbortController();

    const fetchClips = async () => {
      try {
        const res = await fetch(CLIPS_ENDPOINT, { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { clips?: unknown };
        const list = Array.isArray(data.clips)
          ? data.clips.filter((c): c is string => typeof c === 'string' && VIDEO_EXT.test(c))
          : [];
        if (cancelled) return;
        if (list.length === 0) throw new Error('No clips available');
        setClips(list);
      } catch (err) {
        if (cancelled || (err as Error).name === 'AbortError') return;
        console.warn('[overlay] /api/clips failed, retrying…', err);
        retryTimer = window.setTimeout(fetchClips, CLIPS_RETRY_MS);
      }
    };

    fetchClips();
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(retryTimer);
    };
  }, []);

  // Arranque: primer clip en slot A (visible), siguiente precargado en slot B.
  useEffect(() => {
    if (clips.length === 0) return;
    clipsRef.current = clips;
    activeSlotRef.current = 0;
    setActiveSlot(0);

    const first = slotARef.current;
    if (!first) return;
    first.loop = clips.length === 1; // un único clip: loop nativo, sin swaps
    loadInto(0, 0);
    first.play().catch(() => undefined);

    if (clips.length > 1) loadInto(1, pickNextIndex(0, clips.length));
  }, [clips, loadInto]);

  const advance = useCallback(() => {
    const total = clipsRef.current.length;
    const from = activeSlotRef.current;
    const current = getSlot(from);

    if (total <= 1) {
      if (current) {
        current.currentTime = 0;
        current.play().catch(() => undefined);
      }
      return;
    }

    const to: Slot = from === 0 ? 1 : 0;
    const next = getSlot(to);
    if (!next || advancingRef.current) return;

    advancingRef.current = true;
    next.currentTime = 0;
    next
      .play()
      .then(() => {
        advancingRef.current = false;
        // El nuevo clip ya reproduce: swap instantáneo. El anterior queda
        // congelado en su último frame detrás, así que nunca se ve negro.
        activeSlotRef.current = to;
        setActiveSlot(to);
        const upcoming = pickNextIndex(slotClipIndex.current[to], total);
        // Sin rAF: usamos un timeout breve para permitir que el swap se pinte.
        window.setTimeout(() => loadInto(from, upcoming), SWAP_RELOAD_DELAY_MS);
      })
      .catch(() => {
        advancingRef.current = false;
        // El clip en espera falló: repetimos el actual y precargamos otro.
        if (current) {
          current.currentTime = 0;
          current.play().catch(() => undefined);
        }
        loadInto(to, pickNextIndex(slotClipIndex.current[to], total));
      });
  }, [loadInto]);

  const handleError = useCallback(
    (slot: Slot) => {
      const total = clipsRef.current.length;
      if (total === 0) return;
      console.warn('[overlay] clip failed:', clipsRef.current[slotClipIndex.current[slot]]);
      window.setTimeout(() => {
        if (slot === activeSlotRef.current) advance();
        else loadInto(slot, pickNextIndex(slotClipIndex.current[slot], total));
      }, 1000);
    },
    [advance, loadInto],
  );

  // Watchdog de reproducción: Chromium pausa el autoplay y congela rAF/timers
  // cuando la ventana queda oculta; esto la reanuda sola al volver o si pausa.
  useEffect(() => {
    let lastTime = -1;
    let stuckTicks = 0;
    let warnedStuck = false;

    const checkPlayback = () => {
      const active = getSlot(activeSlotRef.current);
      if (!active || clipsRef.current.length === 0) return;

      if (active.ended) {
        // Sin onEnded (timer limitado): forzar el avance manualmente.
        advance();
        return;
      }
      if (active.paused) {
        active.play().catch(() => undefined);
        return;
      }
      if (active.currentTime === lastTime) {
        stuckTicks += 1;
        if (!warnedStuck && stuckTicks >= 2) {
          warnedStuck = true;
          console.warn('[overlay] playback stalled while not paused; forcing play()');
          active.play().catch(() => undefined);
        }
      } else {
        lastTime = active.currentTime;
        stuckTicks = 0;
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return;
      const active = getSlot(activeSlotRef.current);
      if (!active || clipsRef.current.length === 0) return;
      if (active.ended) advance();
      else if (active.paused) active.play().catch(() => undefined);
    };

    const onPause = (e: Event) => {
      const el = e.target as HTMLVideoElement | null;
      if (el === null || el !== getSlot(activeSlotRef.current) || el.ended || clipsRef.current.length === 0) return;
      el.play().catch(() => undefined);
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    const elA = slotARef.current;
    const elB = slotBRef.current;
    elA?.addEventListener('pause', onPause);
    elB?.addEventListener('pause', onPause);
    const watchdog = window.setInterval(checkPlayback, PLAYBACK_WATCHDOG_MS);

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      elA?.removeEventListener('pause', onPause);
      elB?.removeEventListener('pause', onPause);
      window.clearInterval(watchdog);
    };
  }, [advance]);

  const renderSlot = (slot: Slot, ref: RefObject<HTMLVideoElement>) => (
    <video
      ref={ref}
      className="absolute inset-0 h-full w-full object-cover"
      style={{ opacity: activeSlot === slot ? 1 : 0, zIndex: activeSlot === slot ? 1 : 0 }}
      muted
      playsInline
      preload="auto"
      disablePictureInPicture
      onEnded={() => slot === activeSlotRef.current && advance()}
      onError={() => handleError(slot)}
    />
  );

  return (
    <div className="absolute inset-0 z-0 overflow-hidden bg-black">
      {renderSlot(0, slotARef)}
      {renderSlot(1, slotBRef)}
    </div>
  );
}

/* ============================================================================
 * COMPONENT: Dígitos de 7 segmentos (con segmentos "apagados" de fondo)
 * ==========================================================================*/

function SegDigits({ value, size }: { value: string; size: number }) {
  return (
    <span className="seg relative inline-block leading-none" style={{ fontSize: size }}>
      <span className="seg-ghost absolute inset-0" aria-hidden="true">
        {'8'.repeat(value.length)}
      </span>
      <span className="relative">{value}</span>
    </span>
  );
}

/* ============================================================================
 * COMPONENT: HUD de dados
 * ==========================================================================*/

function DiceHud({
  roll,
  rollId,
  status,
}: {
  roll: DiceRollEvent | null;
  rollId: number;
  status: SocketStatus;
}) {
  const failed = roll !== null && roll.successes === 0;
  const pool = roll ? padDigits(roll.dice_count) : '--';
  const hits = roll ? padDigits(roll.successes) : '--';
  const hitsSize = hits.length <= 2 ? 52 : hits.length === 3 ? 38 : 28;

  return (
    <aside
      className="pointer-events-none absolute bottom-[16px] left-[40px] z-30 select-none"
      style={{ width: HUD_WIDTH }}
      aria-label="Dice HUD"
    >
      <img
        src={HUD_FRAME_URL}
        alt=""
        draggable={false}
        className="hud-frame relative z-0 block h-auto w-full"
      />

      {/* LED de conexión sobre el indicador STATUS del chasis */}
      <span
        className={`hud-status-led hud-status-led--${status}`}
        style={{ left: `${HUD_STATUS_LED.left}%`, top: `${HUD_STATUS_LED.top}%` }}
      />

      {/* Pantalla digital */}
      <div
        className="hud-screen absolute z-10 overflow-hidden"
        style={{
          left: `${HUD_SCREEN.left}%`,
          top: `${HUD_SCREEN.top}%`,
          width: `${HUD_SCREEN.width}%`,
          height: `${HUD_SCREEN.height}%`,
          maskImage: HUD_SCREEN_MASK,
          WebkitMaskImage: HUD_SCREEN_MASK,
        }}
      >
        {/* key={rollId} remonta el contenido -> re-dispara el parpadeo en cada tirada */}
        <div
          key={rollId}
          className={`led ${failed ? 'led--fail' : ''} ${rollId > 0 ? 'hud-flicker' : ''} font-led relative z-10 flex h-full flex-col px-[8px] py-[7px]`}
        >
          {/* Barra superior */}
          <div className="flex items-center justify-between text-[9px] leading-none tracking-[0.18em] opacity-80">
            <span>DICE.SYS</span>
            <span>{status === 'open' ? 'LINK' : 'NO-LINK'}</span>
          </div>
          <div className="led-divider my-[5px]" />

          {/* Jugador */}
          <span className="text-[8px] leading-none tracking-[0.25em] opacity-60">PLAYER</span>
          <span className="mt-[3px] truncate text-[15px] uppercase leading-tight">
            {roll ? roll.user : (
              <>
                AWAITING<span className="cursor-blink">_</span>
              </>
            )}
          </span>

          <div className="led-divider my-[6px]" />

          {/* Reserva de dados */}
          <div className="flex items-end justify-between">
            <span className="pb-[2px] text-[9px] leading-none tracking-[0.2em] opacity-70">
              DICE
              <br />
              POOL
            </span>
            <SegDigits value={pool} size={24} />
          </div>

          <div className="led-divider my-[6px]" />

          {/* Éxitos */}
          <span className="text-[8px] leading-none tracking-[0.25em] opacity-60">SUCCESSES</span>
          <div className="flex flex-1 items-center justify-center">
            <SegDigits value={hits} size={hitsSize} />
          </div>

          {/* Pie */}
          <div className="led-divider mb-[4px]" />
          <div className="text-center text-[10px] leading-none tracking-[0.18em]">
            {!roll ? (
              <span className="opacity-60">STANDBY</span>
            ) : failed ? (
              <span className="crit-blink">✕ NO SUCCESS</span>
            ) : (
              <span>
                {roll.successes} {roll.successes === 1 ? 'SUCCESS' : 'SUCCESSES'}
              </span>
            )}
          </div>
        </div>

        <div className="hud-scanlines pointer-events-none absolute inset-0 z-20" />
        <div className="hud-scanbar pointer-events-none absolute inset-x-0 z-20" />
      </div>
    </aside>
  );
}

/* ============================================================================
 * COMPONENT: HUD de voz (siempre visible, abajo a la derecha)
 * ==========================================================================*/

function VoiceHud({
  voice,
  status,
}: {
  voice: VoiceStateEvent | null;
  status: SocketStatus;
}) {
  const inStandby = voice === null || voice.channel === null;
  const members = inStandby ? [] : voice.members;
  const speaking = members.filter((m) => m.speaking);
  const rest = members.filter((m) => !m.speaking);
  // Prioriza a quien habla: hablantes primero, luego el resto, en orden recibido.
  const ordered = [...speaking, ...rest];
  const hasMore = ordered.length > VOICE_MAX_ROWS;
  const visible = hasMore ? ordered.slice(0, VOICE_MAX_ROWS - 1) : ordered;
  const hiddenCount = hasMore ? ordered.length - (VOICE_MAX_ROWS - 1) : 0;

  return (
    <aside
      className="pointer-events-none absolute bottom-[16px] right-[40px] z-30 select-none"
      style={{ width: VOICE_HUD_WIDTH }}
      aria-label="Voice HUD"
    >
      <img
        src={VOICE_FRAME_URL}
        alt=""
        draggable={false}
        className="hud-frame relative z-0 block h-auto w-full"
      />

      {/* Pantalla digital */}
      <div
        className="hud-screen absolute z-10 overflow-hidden"
        style={{
          left: `${VOICE_HUD_SCREEN.left}%`,
          top: `${VOICE_HUD_SCREEN.top}%`,
          width: `${VOICE_HUD_SCREEN.width}%`,
          height: `${VOICE_HUD_SCREEN.height}%`,
        }}
      >
        <div className="led font-led relative z-10 flex h-full flex-col px-[8px] py-[7px]">
          {/* Barra superior */}
          <div className="flex items-center justify-between text-[9px] leading-none tracking-[0.18em] opacity-80">
            <span>VOICE.SYS</span>
            <span>{status === 'open' ? 'LINK' : 'NO-LINK'}</span>
          </div>
          <div className="led-divider my-[5px]" />

          {/* Canal */}
          <span className="text-[8px] leading-none tracking-[0.25em] opacity-60">CHANNEL</span>
          <span className="mt-[3px] truncate text-[15px] uppercase leading-tight">
            {inStandby ? (
              <>
                NO VOICE<span className="cursor-blink">_</span>
              </>
            ) : (
              voice.channel
            )}
          </span>

          <div className="led-divider my-[6px]" />

          {/* Miembros */}
          <div className="flex-1 overflow-hidden">
            {members.length === 0 ? (
              <span className="text-[11px] leading-none opacity-60">
                {inStandby ? '' : 'EMPTY'}
              </span>
            ) : (
              visible.map((m) => (
                <div
                  key={m.id}
                  className={`flex items-center truncate text-[11px] leading-tight ${m.speaking ? 'voice-speaking' : 'opacity-55'}`}
                >
                  <span className="voice-icon inline-block w-[1.9em]">
                    {m.speaking ? VOICE_ICON_SPEAKING : VOICE_ICON_SILENT}
                  </span>
                  <span className="truncate uppercase">{m.name}</span>
                </div>
              ))
            )}
            {hasMore && (
              <div className="truncate text-[10px] leading-tight opacity-60">
                +{hiddenCount} MORE
              </div>
            )}
          </div>

          {/* Pie */}
          <div className="led-divider mb-[4px]" />
          <div className="text-center text-[10px] leading-none tracking-[0.18em]">
            {inStandby ? (
              <span className="opacity-60">STANDBY</span>
            ) : speaking.length === 0 ? (
              <span>{members.length} IN VOICE</span>
            ) : (
              <span>
                {members.length} IN VOICE · {speaking.length} TALKING
              </span>
            )}
          </div>
        </div>

        <div className="hud-scanlines pointer-events-none absolute inset-0 z-20" />
        <div className="hud-scanbar pointer-events-none absolute inset-x-0 z-20" />
      </div>
    </aside>
  );
}

/* ============================================================================
 * COMPONENT: Elemento multimedia con fallback img <-> video
 * Si el primer intento falla (p. ej. un ".gif" que en realidad es MP4), se
 * reintenta una vez con el otro tipo de elemento antes de descartarlo.
 * ==========================================================================*/

const MEDIA_ELEMENT_CLASS =
  'block h-auto min-h-[360px] max-h-[560px] w-auto max-w-[860px] object-contain';

function MediaElement({
  item,
  onReady,
  onFail,
}: {
  item: MediaItem;
  onReady: () => void;
  onFail: () => void;
}) {
  const [asVideo, setAsVideo] = useState(item.isVideo);
  const [retried, setRetried] = useState(false);

  const handleError = () => {
    if (retried) {
      console.warn('[overlay] media no reproducible:', item.url);
      onFail();
      return;
    }
    setRetried(true);
    setAsVideo((v) => !v);
  };

  return asVideo ? (
    <video
      key="video"
      src={item.url}
      autoPlay
      muted
      loop
      playsInline
      disablePictureInPicture
      onLoadedData={onReady}
      onError={handleError}
      className={MEDIA_ELEMENT_CLASS}
    />
  ) : (
    <img
      key="img"
      src={item.url}
      alt={`Media enviada por ${item.user}`}
      decoding="async"
      onLoad={onReady}
      onError={handleError}
      className={MEDIA_ELEMENT_CLASS}
    />
  );
}

/* ============================================================================
 * COMPONENT: Escenario de imágenes / GIFs (animaciones estilo PowerPoint)
 * ==========================================================================*/

function MediaStage({
  item,
  phase,
  onReady,
  onFail,
}: {
  item: MediaItem | null;
  phase: MediaPhase;
  onReady: () => void;
  onFail: () => void;
}) {
  if (!item) return null;

  // 'loading' = invisible hasta que el archivo carga (evita animar un hueco vacío)
  const animClass =
    phase === 'loading' ? 'opacity-0' : phase === 'in' ? `ppt-in-${item.anim}` : 'ppt-out';

  return (
    <section
      className="pointer-events-none absolute right-[120px] top-[110px] z-20 flex h-[640px] w-[900px] items-center justify-center"
      style={{ perspective: '1200px' }}
      aria-live="polite"
    >
      <figure key={item.id} className={`m-0 flex flex-col items-center ${animClass}`}>
        <div className="media-frame relative">
          <MediaElement item={item} onReady={onReady} onFail={onFail} />
          <span className="media-corner media-corner--tl" />
          <span className="media-corner media-corner--tr" />
          <span className="media-corner media-corner--bl" />
          <span className="media-corner media-corner--br" />
        </div>
        <figcaption className="media-caption font-led mt-[14px]">
          <span className="opacity-60">SENT BY ▸</span> {item.user}
        </figcaption>
      </figure>
    </section>
  );
}

/* ============================================================================
 * ROOT
 * ==========================================================================*/

export default function App() {
  const [roll, setRoll] = useState<DiceRollEvent | null>(null);
  const [rollId, setRollId] = useState(0);
  const [voice, setVoice] = useState<VoiceStateEvent | null>(null);
  const [voiceAt, setVoiceAt] = useState(0);
  const { current, phase, enqueue, onReady, onFail } = useMediaQueue();

  const handleEvent = useCallback(
    (evt: OverlayEvent) => {
      switch (evt.type) {
        case 'DICE_ROLL':
          setRoll(evt);
          setRollId((n) => n + 1);
          break;
        case 'NEW_MEDIA':
          enqueue(evt.url, evt.user, evt.media_type);
          break;
        case 'VOICE_STATE':
          setVoice(evt.channel === null ? null : evt);
          setVoiceAt(Date.now());
          break;
      }
    },
    [enqueue],
  );

  // Caducidad: sin latidos durante VOICE_STALE_MS, vuelve a STANDBY.
  useEffect(() => {
    if (voiceAt === 0) return;
    const t = window.setTimeout(() => setVoice(null), VOICE_STALE_MS);
    return () => window.clearTimeout(t);
  }, [voiceAt]);

  const status = useOverlaySocket(handleEvent);
  const voiceForHud = status === 'open' ? voice : null;

  return (
    <main className="relative h-[1080px] w-[1920px] overflow-hidden">
      <h1 className="sr-only">SuperRolScreen — Overlay de partida de rol</h1>
      <GameplayLoop />
      <MediaStage item={current} phase={phase} onReady={onReady} onFail={onFail} />
      <DiceHud roll={roll} rollId={rollId} status={status} />
      <VoiceHud voice={voiceForHud} status={status} />
    </main>
  );
}
