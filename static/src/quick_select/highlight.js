/**
 * Accent and case insensitive normalisation of one character ("Á" -> "a").
 */
function normalizeChar(char) {
    return char.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/**
 * Split ``text`` into ``[{text, match}]`` segments marking every occurrence of
 * the search words, ignoring case and accents, like the server-side search.
 * Segments are rendered with t-esc, so no HTML is ever injected.
 */
export function highlightSegments(text, words) {
    text = text || "";
    const needles = (words || []).map((word) => [...word].map(normalizeChar).join("")).filter(Boolean);
    if (!needles.length) {
        return [{ text, match: false }];
    }
    // Normalised text plus, for each of its characters, the index of the
    // original character it comes from.
    let normalized = "";
    const origin = [];
    [...text].forEach((char, index) => {
        for (const piece of normalizeChar(char)) {
            normalized += piece;
            origin.push(index);
        }
    });
    const chars = [...text];
    const marked = new Array(chars.length).fill(false);
    for (const needle of needles) {
        let from = normalized.indexOf(needle);
        while (from !== -1) {
            for (let i = from; i < from + needle.length; i++) {
                marked[origin[i]] = true;
            }
            from = normalized.indexOf(needle, from + needle.length);
        }
    }
    const segments = [];
    chars.forEach((char, index) => {
        const last = segments[segments.length - 1];
        if (last && last.match === marked[index]) {
            last.text += char;
        } else {
            segments.push({ text: char, match: marked[index] });
        }
    });
    return segments;
}
