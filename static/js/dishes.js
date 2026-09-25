// Zonder foto krijgt elk gerecht een passend icoon op een zachte pastelkleur.
import { esc } from "./util.js";

export const DISHES = [
  [/pasta|spaghetti|lasagne|penne|macaroni|tagliatelle|ravioli|gnocchi/, "🍝"],
  [/ramen|noedel|noodle|mie\b|pho|wok|pad thai/, "🍜"],
  [/curry|dahl|dal\b|korma|masala/, "🍛"],
  [/soep|bouillon|chili/, "🍲"],
  [/salade|bowl/, "🥗"],
  [/zalm|vis|kabeljauw|tonijn|garnal|mossel|scampi|schelvis|pangasius/, "🐟"],
  [/pizza|flammkuchen/, "🍕"],
  [/burger/, "🍔"],
  [/taco|wrap|burrito|quesadilla|fajita|tortilla/, "🌮"],
  [/shakshuka|omelet|frittata|\bei\b|eieren|quiche/, "🍳"],
  [/stamppot|aardappel|puree|hutspot|zuurkool/, "🥔"],
  [/kip|chicken|kalkoen/, "🍗"],
  [/biefstuk|steak|rund|gehakt|worst|varken|lam|stoof/, "🥩"],
  [/rijst|risotto|nasi|paella|sushi/, "🍚"],
  [/ovenschotel|stoofpot|tajine|casserole/, "🥘"],
  [/brood|tosti|sandwich|pannenkoek/, "🥪"],
  [/tofu|tempeh|vegan|groente|linzen|kikkererwt|bonen/, "🥦"],
];

// Pastel roze, mint en crème.
const PLATES = ["#fde4ec", "#e3f4e8", "#fff1dc", "#f6e3f3", "#e6f3ee", "#fbe9e1", "#eef6dc", "#fdeef3"];

export function dishFor(item) {
  const text = `${item.name} ${item.tags ?? ""}`.toLowerCase();
  return DISHES.find(([re]) => re.test(text))?.[1] ?? "🍽️";
}

export function plateAttrs(item, cls = "plate") {
  return item.image
    ? `class="${cls} photo" style="background-image: url('${esc(item.image)}')"`
    : `class="${cls}" style="--plate: ${plateFor(item)}"`;
}

export function plateFor(item) {
  let hash = 0;
  for (const ch of item.name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PLATES[hash % PLATES.length];
}

// Avonden zonder recept.
export const SPECIALS = {
  vriezer: { emoji: "🧊", label: "Uit de vriezer", line: "Makkelijk: iets uit de vriezer" },
  uiteten: { emoji: "🍽️", label: "Uit eten", line: "Lekker de deur uit" },
  afhalen: { emoji: "🥡", label: "Afhalen", line: "Afhalen of laten bezorgen" },
  restjes: { emoji: "🍲", label: "Restjes", line: "Op met wat er nog staat" },
};

export function specialFor(kind) {
  return SPECIALS[kind] ?? { emoji: "🍽️", label: kind, line: "" };
}
