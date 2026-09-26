// Sample Q&A shown in the landing "See it answer" section. Values are
// approximate public figures, rounded — a preview, not live query output.

export type ShowcaseExample = {
  question: string;
  answer: string;
  source: string;
  unit: string;
  chart: "area" | "bar" | "line";
  data: { label: string; value: number }[];
  highlight?: string[];
  /** Fixed y-axis range; defaults to 0 → auto. */
  yDomain?: [number, number];
};

export const showcaseExamples: ShowcaseExample[] = [
  {
    question: "How much has Arctic sea ice declined since 2000?",
    answer:
      "September Arctic sea ice extent fell from about 6.3M km² in 2000 to about 4.3M km² in 2024, roughly a third smaller.",
    source: "NSIDC Sea Ice Index",
    unit: "M km²",
    chart: "area",
    data: [
      { label: "2000", value: 6.32 },
      { label: "2002", value: 5.96 },
      { label: "2004", value: 6.05 },
      { label: "2006", value: 5.89 },
      { label: "2007", value: 4.27 },
      { label: "2008", value: 4.69 },
      { label: "2010", value: 4.9 },
      { label: "2012", value: 3.57 },
      { label: "2014", value: 5.28 },
      { label: "2016", value: 4.72 },
      { label: "2018", value: 4.79 },
      { label: "2020", value: 3.92 },
      { label: "2022", value: 4.87 },
      { label: "2024", value: 4.28 },
    ],
  },
  {
    question: "Compare 2023 vs 2024 wildfire acreage in Canada",
    answer:
      "Canada burned about 42M acres in 2023, its worst season on record, versus about 13M acres in 2024. That's roughly a third of the 2023 total, but still high by historical standards.",
    source: "CIFFC / Natural Resources Canada",
    unit: "M acres",
    chart: "bar",
    highlight: ["2023", "2024"],
    data: [
      { label: "2019", value: 4.4 },
      { label: "2020", value: 0.6 },
      { label: "2021", value: 10.4 },
      { label: "2022", value: 4.0 },
      { label: "2023", value: 42.5 },
      { label: "2024", value: 13.1 },
    ],
  },
  {
    question: "CO₂ concentration at Mauna Loa over the last 50 years",
    answer:
      "Atmospheric CO₂ at Mauna Loa rose from about 331 ppm in 1975 to about 425 ppm in 2024, a 28% increase. The yearly rise has sped up from ~1.5 to ~2.5 ppm.",
    source: "NOAA Global Monitoring Laboratory",
    unit: "ppm",
    chart: "line",
    yDomain: [320, 440],
    data: [
      { label: "1975", value: 331.4 },
      { label: "1980", value: 338.9 },
      { label: "1985", value: 346.4 },
      { label: "1990", value: 354.4 },
      { label: "1995", value: 361 },
      { label: "2000", value: 369.7 },
      { label: "2005", value: 380 },
      { label: "2010", value: 390.1 },
      { label: "2015", value: 401 },
      { label: "2020", value: 414.2 },
      { label: "2024", value: 424.6 },
    ],
  },
];
