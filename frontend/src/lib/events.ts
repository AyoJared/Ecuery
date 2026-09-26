// Notable historical events shown on the landing globe. Figures are
// approximate; swap for live feeds (NOAA NHC, NIFC, OpenAQ) once the backend exists.

export type EventType = "cyclone" | "tornado" | "wildfire" | "air";

export const eventTypes: Record<
  EventType,
  { label: string; singular: string; color: string; rgb: string }
> = {
  cyclone: { label: "Tropical cyclones", singular: "Tropical cyclone", color: "#7dd3fc", rgb: "125, 211, 252" },
  tornado: { label: "Tornadoes", singular: "Tornado", color: "#c084fc", rgb: "192, 132, 252" },
  wildfire: { label: "Wildfires", singular: "Wildfire", color: "#fb923c", rgb: "251, 146, 60" },
  air: { label: "Air quality", singular: "Air quality", color: "#facc15", rgb: "250, 204, 21" },
};

export type EnvEvent = {
  id: string;
  type: EventType;
  name: string;
  place: string;
  date: string;
  lat: number;
  lng: number;
  stat: string;
  summary: string;
  question: string;
};

export const envEvents: EnvEvent[] = [
  {
    id: "milton-2024",
    type: "cyclone",
    name: "Hurricane Milton",
    place: "Gulf of Mexico → Florida",
    date: "Oct 2024",
    lat: 24.5,
    lng: -86,
    stat: "~180 mph peak winds",
    summary: "Exploded to Category 5 over the Gulf before landfall near Siesta Key.",
    question: "How fast did Hurricane Milton intensify?",
  },
  {
    id: "otis-2023",
    type: "cyclone",
    name: "Hurricane Otis",
    place: "Acapulco, Mexico",
    date: "Oct 2023",
    lat: 16.8,
    lng: -99.9,
    stat: "Tropical storm → Cat 5 in about a day",
    summary: "One of the fastest intensifications on record, catching forecasts off guard.",
    question: "Which hurricanes intensified fastest in the last decade?",
  },
  {
    id: "haiyan-2013",
    type: "cyclone",
    name: "Typhoon Haiyan",
    place: "Philippines",
    date: "Nov 2013",
    lat: 11.2,
    lng: 125,
    stat: "Among the strongest landfalls ever recorded",
    summary: "Storm surge devastated Tacloban and much of the Eastern Visayas.",
    question: "How have Western Pacific typhoon intensities changed since 1980?",
  },
  {
    id: "freddy-2023",
    type: "cyclone",
    name: "Cyclone Freddy",
    place: "Mozambique & Malawi",
    date: "Feb–Mar 2023",
    lat: -17.9,
    lng: 37,
    stat: "Longest-lived tropical cyclone on record",
    summary: "Crossed the entire southern Indian Ocean and made landfall twice.",
    question: "How long do tropical cyclones last in the Indian Ocean on average?",
  },
  {
    id: "rolling-fork-2023",
    type: "tornado",
    name: "Rolling Fork tornado",
    place: "Mississippi, USA",
    date: "Mar 2023",
    lat: 32.9,
    lng: -90.9,
    stat: "EF4",
    summary: "A long-track nighttime tornado through the Mississippi Delta.",
    question: "How many EF4+ tornadoes hit the US each year since 2000?",
  },
  {
    id: "moore-2013",
    type: "tornado",
    name: "Moore tornado",
    place: "Oklahoma, USA",
    date: "May 2013",
    lat: 35.3,
    lng: -97.5,
    stat: "EF5",
    summary: "Struck the same city hit by an F5 in 1999.",
    question: "Is Tornado Alley shifting east?",
  },
  {
    id: "canada-2023",
    type: "wildfire",
    name: "Canada wildfire season",
    place: "Québec & across Canada",
    date: "2023",
    lat: 50.5,
    lng: -75.5,
    stat: "~17M hectares burned",
    summary: "Canada's worst season on record; smoke reached New York and Europe.",
    question: "Compare 2023 vs 2024 wildfire acreage in Canada",
  },
  {
    id: "lahaina-2023",
    type: "wildfire",
    name: "Lahaina fire",
    place: "Maui, Hawaii",
    date: "Aug 2023",
    lat: 20.9,
    lng: -156.7,
    stat: "Deadliest US wildfire in over a century",
    summary: "Wind-driven fire destroyed most of the historic town of Lahaina.",
    question: "How has drought in Hawaii changed over the last 30 years?",
  },
  {
    id: "black-summer-2019",
    type: "wildfire",
    name: "Black Summer",
    place: "New South Wales, Australia",
    date: "2019–20",
    lat: -35.7,
    lng: 150,
    stat: "Over 17M hectares burned",
    summary: "Months of fires across southeastern Australia after record heat and drought.",
    question: "Hottest year on record in Australia",
  },
  {
    id: "delhi-2024",
    type: "air",
    name: "Delhi smog",
    place: "New Delhi, India",
    date: "Nov 2024",
    lat: 28.6,
    lng: 77.2,
    stat: "Daily AQI near 500 (\"severe\")",
    summary: "Crop burning, traffic and still winter air trapped pollution over the city.",
    question: "What was the AQI in Delhi last November?",
  },
];
