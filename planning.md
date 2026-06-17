# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
- This tool searches the secondhand listings dataset for clothing items that match the user’s request. It helps FitFindr find items based on description, size, and budget. 

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): A short description of the item the user wants, such as style, color, or type of clothing.  
- `size` (str): The clothing size the user is looking for.  
- `max_price` (float): The highest price the user is willing to pay.  

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
Returns a list of matching items, where each result can include the product name, size, price, store or source, and any short description.
 

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
 If no listings match, the agent should tell the user that no results were found and either suggest broadening the search or retry with looser filters.

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
This tool suggests one or more outfit ideas using the selected item and the user’s wardrobe. It helps the agent explain how the new item could actually be worn.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A clothing item selected from the listings results. 
- `wardrobe` (dict): The user’s existing clothing items that can be styled with the new item. 
...
**What it returns:**
<!-- Describe the return value -->
- Returns one or more outfit suggestions, such as a full look or a short list of pieces that pair well with the selected item.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
- If the wardrobe is empty or too limited, the agent should give a simple fallback outfit idea and ask the user for more wardrobe details if needed.  

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
- This tool turns the selected item and outfit suggestion into a short, shareable caption. It gives the user a final styled result instead of only a plain recommendation.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (dict): 
- The outfit combination created by the outfit suggestion tool.

**What it returns:**
<!-- Describe the return value -->
- Returns a short fit card or caption that describes the outfit for using on social media.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
- The agent should tell the user it needs more styling details and avoid generating a broken caption.

---

### Additional Tools (if any)

### Tool 4: relax_search

**What it does:**  
- This optional tool slightly loosens the original search filters when no results are found. It helps the agent retry instead of stopping right away.

**Input parameters:**  
- `description` (str): The original item description from the user.  
- `size` (str): The original size filter.  
- `max_price` (float): The original budget limit.  

**What it returns:**  
- Returns adjusted search filters, such as a broader description, no size filter, or a slightly higher price limit.

**What happens if it fails or returns nothing:**  
- If it cannot improve the search, the agent should explain that no strong matches were found and ask the user to change or expand on their query request.

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

The loop always starts by parsing the user's query with regex to extract a description, size, and max_price, then calls `search_listings()` with those values. After that call there is one conditional decision point: if `search_results` is empty, the loop calls `relax_search()` to loosen the filters and retries `search_listings()` once. Only if that retry is also empty (or `relax_search()` returns `None` because nothing can be loosened) does the loop set `session["error"]` and return early. If results exist (on the first try or the retry), execution continues in a fixed sequence: select the top result, call `suggest_outfit()` with that item and the user's wardrobe, then call `create_fit_card()` with the outfit suggestion. There is no further looping — once `create_fit_card()` returns, the session is complete and the loop is done.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

All state lives in a single `session` dict created by `_new_session()` at the start of every run. Each tool writes its output into a dedicated key: `search_listings()` → `session["search_results"]`, the selection step → `session["selected_item"]`, `suggest_outfit()` → `session["outfit_suggestion"]`, and `create_fit_card()` → `session["fit_card"]`. Each subsequent tool reads from the key the previous step wrote — `suggest_outfit` receives `session["selected_item"]`; `create_fit_card` receives `session["outfit_suggestion"]`. The special key `session["error"]` acts as a stop signal: if it is set to a non-None string at any point, the caller knows the interaction ended early and the output fields will be `None`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Call `relax_search()` to loosen the filters and retry `search_listings()` once; set `session["error"]` and return only if the retry is also empty (or `relax_search()` returns `None`) |
| suggest_outfit | Wardrobe is empty | Call the LLM with a general-styling prompt instead of a wardrobe-specific one; do not set `session["error"]` — the tool still returns a suggestion |
| create_fit_card | Outfit input is empty or whitespace | Guard at the top of the function: set `session["error"]` and return before calling the LLM |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

Mermaid diagram: 

     flowchart TD
    A{User Query} --> B(Planning Loop)

    B --> C[["search_listings(description, size, max_price)"]]

    C -->|"results = []"| R[["relax_search(description, size, max_price)"]]
    R --> R1["Session: adjusted_filters"]
    R1 --> C2[["search_listings(description, size, max_price)"]]
    C2 -->|"results = []"| D["ERROR: No listings found → ask user to broaden request"]

    C -->|"results = [item, ...]"| E["Session: selected_item = results[0]"]
    C2 -->|"results = [item, ...]"| E

    E --> F[["suggest_outfit(selected_item, wardrobe)"]]
    F -->|"wardrobe empty/minimal"| G["Session: fallback_outfit = simple look + wardrobe gap note"]
    F -->|"outfits = [outfit, ...]"| H["Session: selected_outfit = outfits[0]"]

    G --> I[["create_fit_card(fallback_outfit, selected_item)"]]
    H --> I

    I --> J["Session: fit_card = generated caption"]
    J --> K([Return session])
  

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on


     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->


**Milestone 3 — Individual tool implementations:**
: I’ll use Claude to help implement each FitFindr tool from its spec in planning.md: `search_listings`, `suggest_outfit`, `create_fit_card`, and the optional fallback tool. I’ll give it each tool’s inputs, return value, and failure mode, then verify the generated code matches the function signature, handles edge cases correctly, and passes a few direct tests before I trust it.

**Milestone 4 — Planning loop and state management:**
: I’ll use Claude to help build the agent’s planning loop using my Mermaid diagram, tool specs, and session-state design as input. I’ll verify that the loop chooses tools based on previous outputs, stores results like `selected_item` and `fit_card` across steps, and correctly handles fallback paths such as no search results or a minimal wardrobe before moving on.  

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
: The agent first examines the user's query, extracts search constraints, and calls search_listings("vintage graphic tee", size=None, max_price=30)'. This tool returns a list of matching secondhand items, and the agent stores the search results in session state so later tools can use them.

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
: If results are found, the agent selects one item from the returned list and saves it as `selected_item` in the session. It then calls `suggest_outfit(selected_item, wardrobe)` using the item from Step 1 and the wardrobe details from the user’s query, and this returns one or more outfit ideas or a fallback suggestion if the wardrobe is minimal.

**Step 3:**
<!-- Continue until the full interaction is complete -->
: The agent takes the selected outfit suggestion from Step 2, stores it in session state, and calls `create_fit_card(selected_outfit, selected_item)`. This tool generates a shareable caption-style description for the outfit, which becomes the final output.

**Final output to user:**
<!-- What does the user actually see at the end? -->
: The user sees a matching secondhand item, a suggestion for how to style it with their wardrobe, and a final fit card caption. If the search finds nothing or the wardrobe is too limited, the agent gives a fallback response instead of just failing.