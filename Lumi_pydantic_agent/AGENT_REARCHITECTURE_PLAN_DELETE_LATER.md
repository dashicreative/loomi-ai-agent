# Lumi Recipe Agent Re-Architecture Plan
## Discovery vs Strict Mode Implementation - DELETE LATER

---

## 🎯 CORE PHILOSOPHICAL SHIFT

### FROM: Surgical Precision Agent
- Returns 4 "perfect" recipes that match constraints
- Heavy LLM constraint verification
- Deterministic results (same query = same recipes)
- Slow but precise (15-20 seconds)

### TO: Search Engine + Surgical Hybrid
- **Discovery Mode**: 15+ good recipes, ranked by quality, exploratory
- **Strict Mode**: 4-8 precise recipes with heavy constraint verification
- **Intent Detection**: Agent decides mode based on query complexity
- **Speed Optimized**: Discovery ≤8s, Strict ≤15s

---

## 🧠 INTENT DETECTION STRATEGY

### Discovery Triggers (Broad/Exploratory)
- "Find me dinner recipes"
- "What's for breakfast?"
- "Show me pasta dishes" 
- "I want something sweet"

### Strict Triggers (Constraint-Heavy)
- "Gluten-free vegan dessert under 300 calories"
- "Keto dinner with 25g protein, no nuts"
- "Quick lunch recipes under 20 minutes"

### Follow-up Constraint Handling
**User Flow:**
```
User: "Find me dinner recipes" (Discovery)
Agent: Shows 15 varied results
User: "Show me ones with 20g+ protein" (NEW Strict Search)
```

**Decision**: Follow-up constraints = NEW strict search (not filtering existing results)
**Reasoning**: User likely didn't find what they needed, wants different recipes that meet requirements

---

## 🛠️ TOOL ARCHITECTURE CHANGES

### Current Single-Tool Approach
```
search_and_parse_recipes() -> Heavy LLM verification for all
```

### New Dual-Tool Approach
```
discovery_search_and_parse() -> Light filtering, quality ranking, speed optimized
strict_search_and_parse() -> Heavy LLM verification, precise matching
```

### Tool Optimization Strategy

**Discovery Tools:**
- ❌ Skip URL Classification LLM calls → Use hard-coded pattern matching
- ❌ Skip Constraint Verification LLM calls → Use hard-coded quality scoring
- ✅ Increase search volume (40-60 URLs vs 25)
- ✅ Add randomization to prevent deterministic results
- ✅ Simplified parsing for speed

**Strict Tools:**
- ✅ Enhanced LLM verification → More thorough constraint checking
- ✅ Advanced filtering → Multiple LLM validation rounds
- ✅ Deeper parsing → Detailed nutrition/ingredient data
- ✅ Stricter quality gates → Higher thresholds for inclusion

---

## 📁 NEW FILE STRUCTURE

```
/src/
├── /discovery_tools/          # Fast, broad, exploratory
│   ├── discovery_search_tool.py
│   ├── discovery_classification_tool.py
│   ├── discovery_parsing_tool.py
│   ├── discovery_list_tool.py
│   └── discovery_composer.py
├── /strict_tools/             # Precise, thorough, constraint-heavy
│   ├── strict_search_tool.py
│   ├── strict_classification_tool.py
│   ├── strict_parsing_tool.py
│   ├── strict_list_tool.py
│   └── strict_composer.py
├── /shared_tools/             # Common utilities
│   ├── performance_scorer.py
│   ├── nutrition_formatter.py
│   └── memory_manager.py
└── /agents/
    └── hybrid_agent.py        # Single agent with intent detection
```

---

## 💾 SESSION MEMORY ENHANCEMENTS

### Enhanced Recipe Memory Structure
```python
recipe_memory[recipe_id] = {
    # Existing recipe data
    "title": "...",
    "ingredients": [...],
    # NEW metadata
    "search_mode": "discovery" | "strict",
    "query_id": "search_001", 
    "intent_id": "intent_001",
    "shown_to_user": True,
    "timestamp": time.time()
}
```

### Smart Deduplication Logic
```
Discovery → Discovery: ❌ Block duplicates (keep exploration fresh)
Strict → Strict: ❌ Block duplicates (don't repeat precise results)
Discovery → Strict: ✅ Allow overlaps (recipe might meet strict requirements)
Strict → Discovery: ✅ Allow overlaps (user switching to exploratory)
```

### Session Exclusion Sets
```python
session_shown_urls_discovery = set()  # URLs shown in discovery searches
session_shown_urls_strict = set()     # URLs shown in strict searches

# Exclusion logic per mode
if current_mode == "discovery":
    exclude_urls = session_shown_urls_discovery
elif current_mode == "strict": 
    exclude_urls = session_shown_urls_strict
```

---

## 🎯 AGENT ORCHESTRATION

### Single Intelligent Agent
- **Intent Classification**: Analyze query complexity automatically
- **Tool Selection**: Choose discovery vs strict tools based on intent
- **Context Awareness**: Track conversation flow and previous results
- **Seamless Transitions**: Handle mode switching transparently

### System Prompt Strategy
- **Unified Prompt**: Single prompt with intent detection instructions
- **Dynamic Tool Usage**: "Use discovery_tools for broad queries, strict_tools for constrained queries"
- **Conversation Context**: Reference previous searches and results intelligently

---

## 🚀 IMPLEMENTATION PHASES

### Phase 1: Scaffolding Setup ✅ (CURRENT PHASE)
1. Create comprehensive planning document (this file)
2. Set up new folder structure
3. Copy existing tools to discovery/strict folders
4. Rename files and update basic imports
5. Wait for confirmation before implementation

### Phase 2: Discovery Tools Implementation
1. Modify discovery tools to optimize for speed and variety
2. Remove heavy LLM constraint verification
3. Implement quality-based ranking instead of filtering
4. Add randomization to break deterministic patterns
5. Increase result counts (15+ recipes)

### Phase 3: Strict Tools Implementation  
1. Enhance strict tools for precision and constraint verification
2. Add more thorough LLM validation rounds
3. Implement stricter quality gates
4. Optimize for accuracy over speed
5. Maintain lower result counts (4-8 recipes)

### Phase 4: Agent Integration
1. Implement intent detection logic
2. Update system prompt for dual-tool orchestration
3. Integrate smart session exclusion logic
4. Add conversation context awareness
5. Test mode switching scenarios

### Phase 5: Testing & Optimization
1. Test discovery mode performance (target ≤8s)
2. Test strict mode accuracy (constraint satisfaction)
3. Test seamless mode transitions
4. Optimize based on real usage patterns
5. Performance monitoring and analytics

---

## 🔑 CRITICAL DESIGN DECISIONS

### 1. No Explicit Mode Selection
- **Decision**: Agent detects intent automatically
- **Reasoning**: Users think conversationally, not in "modes"
- **Benefit**: Seamless experience, natural flow

### 2. Fresh Search for Follow-up Constraints
- **Decision**: New constraints = new search (not filtering existing)
- **Reasoning**: User likely didn't find what they needed in current results
- **Benefit**: Higher satisfaction, better constraint matching

### 3. Mode-Specific Deduplication
- **Decision**: Separate exclusion sets for discovery vs strict
- **Reasoning**: Same recipe might be relevant in different contexts
- **Benefit**: Don't hide relevant results due to mode switching

### 4. Tool Duplication vs Configuration
- **Decision**: Separate tool files for discovery vs strict
- **Reasoning**: True optimization requires different approaches
- **Benefit**: No compromise, clear separation of concerns

### 5. Single Agent Architecture
- **Decision**: One agent that chooses tools vs separate agents
- **Reasoning**: Simpler conversation context management
- **Benefit**: Seamless mode transitions, unified session state

---

## 📊 SUCCESS METRICS

### Discovery Mode
- **Speed**: ≤8 seconds average
- **Variety**: No deterministic results, good diversity
- **Volume**: 15+ quality recipes per search
- **User Engagement**: Higher exploration rates

### Strict Mode  
- **Accuracy**: >90% constraint satisfaction
- **Precision**: 4-8 highly relevant recipes
- **Speed**: ≤15 seconds average
- **Safety**: 100% allergy/dietary restriction compliance

### Overall
- **Mode Detection**: >95% correct intent classification
- **Transition Smoothness**: Seamless mode switching
- **Session Context**: Intelligent result deduplication
- **User Satisfaction**: Improved task completion rates

---

## 🎭 USER EXPERIENCE SCENARIOS

### Scenario 1: Discovery to Strict
```
User: "Find me dinner recipes"
Agent: [Discovery Mode] 15 varied results in 6 seconds
User: "Show me ones with 25g protein"  
Agent: [Strict Mode] NEW search, 5 high-protein recipes in 12 seconds
```

### Scenario 2: Strict to Discovery
```
User: "Gluten-free vegan dessert under 300 calories"
Agent: [Strict Mode] 4 precise matches in 14 seconds
User: "Actually, show me any chocolate desserts"
Agent: [Discovery Mode] 15 chocolate options in 7 seconds
```

### Scenario 3: Progressive Refinement
```
User: "Quick breakfast ideas"
Agent: [Discovery Mode] 15 quick breakfast recipes
User: "Make it high-protein"
Agent: [Strict Mode] NEW search for high-protein breakfast recipes
User: "Actually, just show me smoothie recipes"  
Agent: [Discovery Mode] NEW search for smoothie variety
```

---

## 🔄 NEXT STEPS

1. **Complete Phase 1**: Finish scaffolding setup
2. **User Confirmation**: Get approval before implementation
3. **Iterative Development**: Build and test each phase incrementally
4. **Performance Monitoring**: Track metrics throughout development
5. **User Testing**: Validate with real usage scenarios

---

*This document captures the complete architectural vision and implementation plan. Delete after successful implementation.*