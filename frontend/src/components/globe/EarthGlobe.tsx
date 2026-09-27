"use client";

// Client-only: react-globe.gl needs WebGL/window. Load via next/dynamic with ssr: false.
import { useEffect, useMemo, useRef } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import { Color, MeshPhongMaterial } from "three";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import countriesTopology from "world-atlas/countries-110m.json";
import { eventTypes, type EnvEvent } from "@/lib/events";
import { hazardSvg } from "@/lib/hazard-icons";

const topology = countriesTopology as unknown as Topology<{ countries: GeometryCollection }>;
const countries = feature(topology, topology.objects.countries).features.map(dropDegeneratePolygons);

// world-atlas quantization leaves a few zero-area slivers (e.g. one in North Korea)
// that make h3's polygonToCells throw. Strip rings with fewer than 3 distinct points.
function dropDegeneratePolygons<F extends { geometry: GeoJSON.Geometry }>(f: F): F {
  if (f.geometry.type !== "MultiPolygon") return f;
  const isReal = (poly: GeoJSON.Position[][]) => new Set(poly[0].map((p) => p.join(","))).size >= 3;
  return { ...f, geometry: { ...f.geometry, coordinates: f.geometry.coordinates.filter(isReal) } };
}

// Atlantic-centred: Americas, Europe and Africa all in view at load.
const HOME_VIEW = { lat: 28, lng: -25, altitude: 1.95 };

type EarthGlobeProps = {
  events: EnvEvent[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  size: number;
  paused: boolean;
  /** Where the camera starts. Defaults to an Atlantic-centred view of the whole globe. */
  homeView?: { lat: number; lng: number; altitude: number };
};

export function EarthGlobe({ events, selectedId, onSelect, size, paused, homeView = HOME_VIEW }: EarthGlobeProps) {
  const globeRef = useRef<GlobeMethods | undefined>(undefined);
  const markers = useRef(new Map<string, HTMLElement>());

  // Marker DOM listeners are created once, so they read the latest values through refs.
  const onSelectRef = useRef(onSelect);
  const selectedIdRef = useRef(selectedId);
  const homeViewRef = useRef(homeView);
  useEffect(() => {
    onSelectRef.current = onSelect;
    selectedIdRef.current = selectedId;
  });

  const material = useMemo(
    () =>
      new MeshPhongMaterial({
        color: "#1a5f96",
        emissive: "#0a2d4d",
        specular: new Color("#5fa8e0"),
        shininess: 14,
      }),
    [],
  );

  function setAutoRotate(on: boolean) {
    const globe = globeRef.current;
    if (globe) globe.controls().autoRotate = on;
  }

  function markerFor(event: EnvEvent) {
    const cached = markers.current.get(event.id);
    if (cached) return cached;

    const meta = eventTypes[event.type];
    const el = document.createElement("button");
    el.type = "button";
    el.className = event.id === selectedIdRef.current ? "gm gm--active" : "gm";
    el.style.setProperty("--c", meta.color);
    el.setAttribute("aria-label", `${event.name}, ${event.place}, ${event.date}`);
    el.innerHTML = `
      <span class="gm-badge">${hazardSvg(event.type, event.lat < 0)}</span>
      <span class="gm-label">${event.name} <span>· ${event.date}</span></span>`;
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      onSelectRef.current(event.id);
    });
    el.addEventListener("pointerenter", () => setAutoRotate(false));
    el.addEventListener("pointerleave", () => setAutoRotate(!selectedIdRef.current));
    markers.current.set(event.id, el);
    return el;
  }

  // One-time camera/controls setup. Done in an effect rather than onGlobeReady,
  // which can fire before the ref is attached.
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    const controls = globe.controls();
    controls.autoRotate = !selectedIdRef.current;
    controls.autoRotateSpeed = 0.45;
    // Let the page keep scrolling: no wheel zoom, and vertical swipes pass through on touch.
    controls.enableZoom = false;
    controls.enablePan = false;
    if (controls.domElement) controls.domElement.style.touchAction = "pan-y";
    globe.pointOfView(homeViewRef.current);
  }, []);

  // Highlight the selected marker, fly to it, and pause spinning while one is selected.
  useEffect(() => {
    markers.current.forEach((el, id) => el.classList.toggle("gm--active", id === selectedId));
    const globe = globeRef.current;
    if (!globe) return;
    const selected = events.find((e) => e.id === selectedId);
    globe.controls().autoRotate = !selected;
    if (selected) globe.pointOfView({ lat: selected.lat, lng: selected.lng, altitude: 1.7 }, 1200);
  }, [selectedId, events]);

  // Stop rendering while the globe is off screen.
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    if (paused) globe.pauseAnimation();
    else globe.resumeAnimation();
  }, [paused]);

  return (
    <Globe
      ref={globeRef}
      width={size}
      height={size}
      backgroundColor="rgba(0,0,0,0)"
      globeMaterial={material}
      showAtmosphere
      atmosphereColor="#7cc4f5"
      atmosphereAltitude={0.16}
      onGlobeClick={() => onSelect(null)}
      hexPolygonsData={countries}
      hexPolygonResolution={3}
      hexPolygonMargin={0.3}
      hexPolygonUseDots
      hexPolygonColor={() => "rgba(222, 238, 214, 0.62)"}
      htmlElementsData={events}
      htmlLat="lat"
      htmlLng="lng"
      htmlAltitude={0.01}
      htmlElement={(d) => markerFor(d as EnvEvent)}
      htmlElementVisibilityModifier={(el, visible) => el.classList.toggle("gm--hidden", !visible)}
      ringsData={events}
      ringLat="lat"
      ringLng="lng"
      ringColor={(d: object) => {
        const rgb = eventTypes[(d as EnvEvent).type].rgb;
        return (t: number) => `rgba(${rgb}, ${0.9 * (1 - t)})`;
      }}
      ringMaxRadius={(d) => ((d as EnvEvent).id === selectedId ? 5 : 3)}
      ringPropagationSpeed={2}
      ringRepeatPeriod={1400}
    />
  );
}
