// Verify cleanMathJaxTriplication destroys AtCoder data
const constraints = "$1 \\leq H \\leq 20$\n$1 \\leq W \\leq 20$\n$\\textrm{move}$ is either\nFirst\nor\nSecond\n, where\nFirst\nmeans that you use the magic first, and\nSecond\nmeans that DEGwer uses the magic first.";

const outputFormat = "Print\nYes\nif your objective is achievable and\nNo\notherwise, under the assumption that you and DEGwer do their best.\nIn addition, if the answer is\nYes\n, print\ninteractively\nin the following format for which doors you use magic. (See also Sample 2.)\n```\n$t$ $i$ $j$\n\n```\n$t$ is either\n|\nor\n-\n.\n$i$ and $j$ are integers.\nIf $t = {}$\n|\n, then $1 \\leq i \\leq H$ and $1 \\leq j \\leq W + 1$, which represents that the door chosen as a target of the magic is the $i$-th from the top and the $j$-th from the left among those which are passed horizontally (i.e., the doors between two horizontally adjacent rooms and all the entrance and exit doors).\nIf $t = {}$\n-\n, then $1 \\leq i \\leq H - 1$ and $1 \\leq j \\leq W$, which represents that the door chosen as a target of the magic is the $i$-th from the top and the $j$-th from the left among those which are passed vertically (i.e., the doors between two vertically adjacent rooms).\nAgainst your output, an input in the same format will be returned.\nNote that if $\\textrm{move} = {}$\nFirst\n, then you should print your output followed by printing\nYes\n, and if $\\textrm{move} = {}$\nSecond\n, then you should receive an input just after printing\nYes\n.\nIn either case,\neach time you print something, end it with a newline and flush Standard Output\n.\n$t$ is one of\n|\n,\n-\n, and\nw\n.\nIf $t$ is either\n|\nor\n-\n, then it represents the door chosen as a target of the magic is the $i$-th from the top and the $j$-th from the left among those which are described as above.\nIf $t$ is\nw\n, then it represents that you are requested to print the verdict of the game. See the next section for details.";

// Exact copy of cleanMathJaxTriplication from crawler.controller.ts
function cleanMathJaxTriplication(text) {
    if (!text) return text;
    {
        const lines = text.split('\n');
        const merged = [];
        let i = 0;
        const MATH_CHAR = /[\\_{}^|×∙∣≤≥±∞∑∏∫∂∇√≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ]/;
        const isMathFragment = (s) => {
            if (!s || s.length > 120) return false;
            if (/^[\[【#]/.test(s)) return false;
            if (/[一-鿿]/.test(s)) return false;
            if (s.length <= 3) {
                return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞∑∏∫∂∇√∞≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ​]+$/.test(s);
            }
            if (!MATH_CHAR.test(s)) return false;
            return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞∑∏∫∂∇√∞≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ​]+$/.test(s);
        };

        while (i < lines.length) {
            const t = lines[i].trim();
            if (t === '' || !isMathFragment(t)) {
                merged.push(lines[i]);
                i++;
                continue;
            }
            const island = [lines[i]];
            i++;
            while (i < lines.length) {
                const s = lines[i].trim();
                if (s === '') {
                    let peek = i + 1;
                    while (peek < lines.length && lines[peek].trim() === '') peek++;
                    if (peek < lines.length && isMathFragment(lines[peek].trim())) {
                        i++;
                        continue;
                    }
                    break;
                }
                if (isMathFragment(s)) {
                    island.push(lines[i]);
                    i++;
                } else {
                    break;
                }
            }
            if (island.length >= 3) {
                const latexLines = island.map(l => l.trim()).filter(l => /\\[a-zA-Z]/.test(l));
                if (latexLines.length > 0) {
                    const best = latexLines.reduce((a, b) => b.length > a.length ? b : a);
                    merged.push(best);
                } else {
                    const unique = [...new Set(island.map(l => l.trim()))];
                    merged.push(unique.reduce((a, b) => b.length > a.length ? b : a));
                }
            } else {
                merged.push(...island.map(l => l.trim()));
            }
        }
        text = merged.join('\n');
    }
    if (!text.includes('$')) {
        text = text.replace(/^(.*\\[a-zA-Z].*)$/gm, (_m, line) => {
            if (line.includes('$')) return _m;
            return '$' + line.trim() + '$';
        });
    }
    text = text.replace(/\\,/g, '').replace(/\\!/g, '').replace(/\\;/g, '').replace(/\\:/g, '')
        .replace(/\$\$/g, '').replace(/\$ \$/g, '')
        .replace(/\n{3,}/g, '\n\n').trim();
    return text;
}

console.log("=== CONSTRAINTS BEFORE ===");
console.log(constraints);
console.log();
console.log("=== CONSTRAINTS AFTER ===");
const cleanedConstraints = cleanMathJaxTriplication(constraints);
console.log(cleanedConstraints);
console.log();
console.log("LOST:", constraints.length - cleanedConstraints.length, "chars");

console.log("\n\n=== OUTPUT FORMAT BEFORE (first 400 chars) ===");
console.log(outputFormat.substring(0, 400));
console.log();
console.log("=== OUTPUT FORMAT AFTER (first 400 chars) ===");
const cleanedOutput = cleanMathJaxTriplication(outputFormat);
console.log(cleanedOutput.substring(0, 400));
console.log();
console.log("LOST:", outputFormat.length - cleanedOutput.length, "chars");
