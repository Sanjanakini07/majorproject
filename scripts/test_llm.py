"""Ask the assistant real questions and check the answers, online (Groq) and offline (local Ollama model).

    .venv\\Scripts\\python scripts\\test_llm.py            # both modes
    .venv\\Scripts\\python scripts\\test_llm.py offline    # or: online

Runs the same steps as /api/ask (exact facts, search, answer) on the database in DATA_DIR. Point DATA_DIR
at a copy of data/ so the real one is never touched. "Offline" is real: every internet connection is sent
to a dead proxy, so the Groq call fails the way it does with Wi-Fi off, and the app must fall back to Ollama.
Each answer is checked for words it must (or must not) contain; read the printed answers too.
"""
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from app import academics, config, db, personal, rag  # noqa: E402
from offline_app import llm  # noqa: E402

EMAIL, NAME = "nnm23is042@nmamit.in", "NNM23IS042 ASHA K RAO"
GAP_SECONDS = 10
NO_INFO = (r"don't have|do not have|not have (that|any|the)|no information|not sure|college office|check with|"
           r"not (been )?(entered|added|available|listed|included|part of)|isn't (listed|available|in)|not yet|"
           r"doesn't (have|include|list)|does not (have|include|list)|here is what the college information says")
A_DATE = r"\b\d{1,2}(st|nd|rd|th)? (of )?(nov|dec|jan)|(november|december|january),? \d"

# (question, regex the answer must match, regex it must NOT match). The second half checks that nothing is made up.
CASES = [
    ("What is my name?", r"asha", None),
    ("What is my USN?", r"nnm23is042", None),
    ("Which semester am I in?", r"\b7|seventh", r"\b6(th)? sem|sixth"),
    ("What is my attendance?", r"\d+(\.\d+)?\s?(percent|%)", None),
    ("How many classes can I miss and still stay above 85 percent?", r"\d", None),
    ("What is my CGPA?", r"\d\.\d|(one|two|three|four|five|six|seven|eight|nine|ten) point", None),
    ("What are the subjects in first semester?", r"(math|physics|chemistry|programming|engineering)", None),
    ("What does unit 2 of operating systems cover?", r"(process|thread|schedul|memory|synchroni|deadlock)", None),
    ("Where can I find DBMS notes?", r"notes", None),
    ("What is the minimum attendance needed to write the SEE?", r"75", None),
    ("How are CIE marks split?", r"(40|forty)", r"diary|viva|40 marks each"),
    ("What grade do I get for 85 percent?", r"a\s?(\+|plus)", None),
    ("I got 38 marks in DBMS, did I pass?", r"fail|did not pass|didn't pass|not pass", r"yes|you passed|you did pass"),
    ("When is the FM SEE?", r"10(th)? (of )?dec|december 10", r"\b15\b|\b12(th)? dec"),
    ("When is the ethical hacking exam?", r"21(st)? (of )?dec|december 21", r"\b10(th)? dec|\b17(th)? dec"),
    ("When is the OOMD SEE?", r"12(th)? (of )?dec|december 12", None),
    ("When is MSE 2?", NO_INFO, A_DATE),
    ("When is the IoT exam?", NO_INFO, A_DATE),
    ("Where is Jason sir's cabin?", r"apj", None),
    ("Who is the HOD?", r"ashwini", None),
    ("Where is Dr. Rashmi Naveen's cabin?", NO_INFO, r"apj|smv|floor \d|\d(st|nd|rd|th) floor"),
    ("What is Mr. Devidas's email?", NO_INFO, r"@"),
    ("Who teaches database management systems?", r"jason|ravi|naganna", None),
    ("When is the Wipfli drive?", r"12(th)? (of )?nov|november 12", None),
    ("What events are coming up?", r"drive|placement|wipfli|infosys|taurani|mathco", None),
    ("When is the next bus to Karkala?", r"\d{1,2}[:.]\d{2}|\d{1,2} ?(am|pm|a\.m|p\.m)", None),
    ("Do I have any class right now?", NO_INFO + r"|\bno\b|sunday|none", r"\d{1,2}[:.]\d{2}"),
    ("When is the library open?", NO_INFO, r"\d"),
    ("What is the hostel fee?", NO_INFO, r"\d"),
    ("What is the capital of France?", NO_INFO, r"paris"),
    ("Who is the principal's wife?", NO_INFO, None),
    ("wat r the electiv subjcts in 6th sem", r"elective", None),
    ("what were my marks last semester?", r"sample", None),
]


def ask(question: str) -> tuple[str, float]:
    t = time.time()
    llm.last_engine = "none"
    facts = personal.build(EMAIL, NAME, question)
    hits = personal.adjust_hits(rag.search(question), facts)
    return llm.answer(question, hits, facts.text), time.time() - t


def run(mode: str) -> int:
    if mode == "offline":
        # A dead proxy for everything except this laptop: Groq can't be reached, Ollama (127.0.0.1) can.
        os.environ.update(HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9",
                          NO_PROXY="127.0.0.1,localhost")
    else:
        for k in ("HTTPS_PROXY", "HTTP_PROXY"):
            os.environ.pop(k, None)
        if not config.GROQ_API_KEY:
            print("GROQ_API_KEY is not set in .env: online mode can't be tested.")
            return 1
    llm._skip_groq_until = 0.0
    print(f"\n===== {mode.upper()} ({'Groq ' + config.GROQ_MODEL if mode == 'online' else 'Ollama'}) =====")
    failed, times, engines = 0, [], []
    for question, must, must_not in CASES:
        if mode == "online":
            # Groq's free plan allows 8,000 tokens a minute; spacing the questions tests Groq, not the limiter.
            time.sleep(GAP_SECONDS)
            llm._skip_groq_until = 0.0
        try:
            ans, secs = ask(question)
        except Exception as e:
            ans, secs = f"ERROR {type(e).__name__}: {e}", 0.0
        times.append(secs)
        ok = bool(re.search(must, ans, re.I)) and not (must_not and re.search(must_not, ans, re.I))
        failed += not ok
        engines.append(llm.last_engine)
        print(f"\n[{'ok' if ok else 'FAIL'}] {secs:5.1f}s {llm.last_engine:5}  Q: {question}\n        A: {ans}")
    print(f"\n{mode}: {len(CASES) - failed}/{len(CASES)} passed, average {sum(times) / len(times):.1f}s, "
          f"slowest {max(times):.1f}s; written by " + ", ".join(f"{e} {engines.count(e)}" for e in sorted(set(engines))))
    return failed


if __name__ == "__main__":
    db.init()
    if not db.get_profile(EMAIL):
        sys.exit(f"No student {EMAIL} in {config.DATA_DIR}: start the app once so the default data is made.")
    academics.adopt_name(EMAIL, NAME)  # what Google sign-in does: the real name replaces the USN placeholder
    modes = sys.argv[1:] or ["online", "offline"]
    sys.exit(1 if sum(run(m) for m in modes) else 0)
