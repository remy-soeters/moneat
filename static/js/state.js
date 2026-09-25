// Gedeelde toestand van de app (wat er geladen is en wat je aan het doen bent).
import { load, mondayOf } from "./util.js";

export const state = {
  tab: "home",
  week: mondayOf(new Date()),
  recipes: [],
  menu: { days: [], options: [], choices: [] },
  household: Number(load("household")) || 2,
  perDay: Number(load("perDay")) || 3,
  filling: null, // {datum: aantal} terwijl de AI bezig is
  picker: { date: null, selected: new Set() },
  view: null, // {option?, recipe?} in de receptweergave
  editMenuDate: null,
  tagFilter: null,
  planTarget: null, // {recipeId, name} of {idea: index} in het inplanvenster
  inspiration: { theme: null, data: null, loading: false, saved: new Map() },
  settings: null,
  home: null, // gegevens van de startpagina
  user: null, // ingelogde gebruiker
  users: [], // accounts in het huishouden (voor de beheerder)
  swipe: { cards: [], stats: null, prefs: null, preload: null, warned: false, poll: null },
  photoBusy: new Set(), // recept-id's of "idea:<index>" waarvoor nu een foto gemaakt wordt
};

export const shop = { items: [], icons: null, suggestions: [], poll: null, hasHistory: false };
