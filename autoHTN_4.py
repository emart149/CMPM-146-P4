import pyhop
import json

def check_enough(state, ID, item, num):
    if getattr(state, item)[ID] >= num:
        return []

    # OPTIMIZATION: Strategic investment (ported from wautoHTN.py)
    # If we need a large amount of basic resources, force an upgrade to a stone pickaxe.
    # This prevents the planner from gathering 20 items with a slow wooden pickaxe.
    if item in ('cobble', 'coal') and num >= 8 and getattr(state, 'stone_pickaxe')[ID] < 1:
        return [('have_enough', ID, 'stone_pickaxe', 1), ('produce', ID, item), ('have_enough', ID, item, num)]

    return [('produce_enough', ID, item, num)]

def produce_enough(state, ID, item, num):
    return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)

def produce(state, ID, item):
    return [('produce_{}'.format(item), ID)]

pyhop.declare_methods('produce', produce)

# --- DETERMINISTIC GATHERING METHODS (Ported from wautoHTN.py) ---
# These prevent the planner from branching into inefficient tools (e.g. punching when you have an axe).

def m_get_wood(state, ID):
    if getattr(state, 'iron_axe')[ID] >= 1:
        return [('op_iron_axe_for_wood', ID)]
    if getattr(state, 'stone_axe')[ID] >= 1:
        return [('op_stone_axe_for_wood', ID)]
    if getattr(state, 'wooden_axe')[ID] >= 1:
        return [('op_wooden_axe_for_wood', ID)]
    return [('op_punch_for_wood', ID)]

def m_get_cobble(state, ID):
    if getattr(state, 'iron_pickaxe')[ID] >= 1:
        return [('op_iron_pickaxe_for_cobble', ID)]
    if getattr(state, 'stone_pickaxe')[ID] >= 1:
        return [('op_stone_pickaxe_for_cobble', ID)]
    if getattr(state, 'wooden_pickaxe')[ID] >= 1:
        return [('op_wooden_pickaxe_for_cobble', ID)]
    return [('have_enough', ID, 'wooden_pickaxe', 1), ('op_wooden_pickaxe_for_cobble', ID)]

def m_get_coal(state, ID):
    if getattr(state, 'iron_pickaxe')[ID] >= 1:
        return [('op_iron_pickaxe_for_coal', ID)]
    if getattr(state, 'stone_pickaxe')[ID] >= 1:
        return [('op_stone_pickaxe_for_coal', ID)]
    if getattr(state, 'wooden_pickaxe')[ID] >= 1:
        return [('op_wooden_pickaxe_for_coal', ID)]
    return [('have_enough', ID, 'wooden_pickaxe', 1), ('op_wooden_pickaxe_for_coal', ID)]

def m_get_ore(state, ID):
    if getattr(state, 'iron_pickaxe')[ID] >= 1:
        return [('op_iron_pickaxe_for_ore', ID)]
    if getattr(state, 'stone_pickaxe')[ID] >= 1:
        return [('op_stone_pickaxe_for_ore', ID)]
    return [('have_enough', ID, 'stone_pickaxe', 1), ('op_stone_pickaxe_for_ore', ID)]

# -----------------------------------------------------------------

def _order_consumes(consumes, dep_map):
    items = list(consumes.keys())
    if len(items) <= 1:
        return items

    item_set = set(items)
    graph = {x: set() for x in items}
    
    for x in items:
        for y in dep_map.get(x, set()):
            if y in item_set and y != x:
                graph[x].add(y)

    indeg = {x: 0 for x in items}
    for x, ys in graph.items():
        for y in ys:
            indeg[y] += 1
            
    queue = [x for x in items if indeg[x] == 0]
    out = []
    
    while queue:
        n = queue.pop()
        out.append(n)
        for y in graph[n]:
            indeg[y] -= 1
            if indeg[y] == 0:
                queue.append(y)
                
    if len(out) != len(items):
        return items 
        
    return out

def make_method(name, rule, tools=None, dep_map=None):
    produces = rule.get("Produces", {})
    requires = rule.get("Requires", {})
    consumes = rule.get("Consumes", {})
    time_cost = rule.get("Time", 0)
    
    dep_map = dep_map or {}
    consumes_order = _order_consumes(consumes, dep_map)

    if 'iron_pickaxe' in produces and 'stick' in consumes and 'ingot' in consumes:
        consumes_order = ['ingot', 'stick']

    def tier(tool_name):
        if tool_name.startswith("wooden_"): return 1
        if tool_name.startswith("stone_"):  return 2
        if tool_name.startswith("iron_"):   return 3
        if tool_name in ("bench", "furnace"): return 0
        return 0

    required_tool_tier = 0
    for item in requires:
        if item in (tools or set()):
            required_tool_tier = max(required_tool_tier, tier(item))

    def method(state, ID):
        subtasks = []
        for item, amount in requires.items():
            subtasks.append(('have_enough', ID, item, amount))

        for item in consumes_order:
             amount = consumes[item]
             subtasks.append(('have_enough', ID, item, amount))

        op_name = 'op_{}'.format(name.replace(' ', '_'))
        subtasks.append((op_name, ID))

        return subtasks

    method.__name__ = 'produce_{}'.format(name.replace(' ', '_'))
    
    method._meta = {
        "tier": required_tool_tier,
        "time": time_cost,
        "n_subtasks": 1 + len(requires) + len(consumes)
    }
    return method

def declare_methods(data):
    tools = set(data.get("Tools", [])) | {"bench", "furnace"}
    
    dep_map = {}
    for rule in data['Recipes'].values():
        for prod in rule.get('Produces', {}):
            dep_map.setdefault(prod, set()).update(rule.get("Consumes", {}).keys())

    rec_prod = {}
    
    for rec_name, rule in data['Recipes'].items():
        for product in rule['Produces']:
            if product not in rec_prod:
                rec_prod[product] = []
            
            mth = make_method(rec_name, rule, tools=tools, dep_map=dep_map)
            rec_prod[product].append(mth)

    for product, method_list in rec_prod.items():
        # Sort generic methods by tier/time
        method_list.sort(key=lambda m: (m._meta["tier"], m._meta["time"], m._meta["n_subtasks"]))
        pyhop.declare_methods('produce_{}'.format(product), *method_list)

    # OVERRIDE: Register deterministic gatherers for raw resources
    # This ensures we use the "Best Tool" logic instead of the generic sorted list
    pyhop.declare_methods("produce_wood", m_get_wood)
    pyhop.declare_methods("produce_cobble", m_get_cobble)
    pyhop.declare_methods("produce_coal", m_get_coal)
    pyhop.declare_methods("produce_ore", m_get_ore)

def make_operator(rule):
    produces = rule.get("Produces", {})
    requires = rule.get("Requires", {})
    consumes = rule.get("Consumes", {})
    time_cost = rule.get("Time", 0)

    def operator(state, ID):
        if state.time[ID] < time_cost:
            return False

        for item, amt in requires.items():
            if getattr(state, item)[ID] < amt:
                return False

        for item, amt in consumes.items():
            if getattr(state, item)[ID] < amt:
                return False

        state.time[ID] -= time_cost
        
        for item, amt in consumes.items():
            curr = getattr(state, item)[ID]
            setattr(state, item, {ID: curr - amt})

        for item, amt in produces.items():
            curr = getattr(state, item)[ID]
            setattr(state, item, {ID: curr + amt})

        return state

    return operator

def declare_operators(data):
    operators_list = []
    for recipe_name, rule in data['Recipes'].items():
        new_operator = make_operator(rule)
        new_operator.__name__ = "op_" + recipe_name.replace(' ', '_')
        operators_list.append(new_operator)

    pyhop.declare_operators(*operators_list)

def add_heuristic(data, ID):
    tool_set = set(data.get("Tools", [])) | {"bench", "furnace"}

    def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
        # Bumped depth limit to 1200 to match wautoHTN
        if depth > 1200:
            return True

        task_name = curr_task[0]
        
        if task_name.startswith('produce_'):
            product = task_name.replace('produce_', '')
            
            if product in tool_set and getattr(state, product)[ID] >= 1:
                return True

            if product in tool_set:
                for upstream_task in calling_stack:
                     if upstream_task[0] == task_name:
                         return True
                         
        return False

    pyhop.add_check(heuristic)

def define_ordering(data, ID):
    def reorder_methods(state, curr_task, tasks, plan, depth, calling_stack, methods):
        return methods
    pyhop.define_ordering(reorder_methods)

def set_up_state(data, ID, time=0):
    state = pyhop.State('state')
    state.time = {ID: time}

    for item in data['Items']:
        setattr(state, item, {ID: 0})

    for item in data['Tools']:
        setattr(state, item, {ID: 0})

    problem_data = data.get('Problem', data)
    initial_data = problem_data.get('Initial', {})

    for item, num in initial_data.items():
        setattr(state, item, {ID: num})

    return state

def solve_test_case(data, initial_items, goal_items, max_time, case_name):
    print(f"\n{'='*20} Solving Case: {case_name} {'='*20}")
    print(f"Initial: {initial_items}")
    print(f"Goal: {goal_items}")
    print(f"Time Limit: {max_time}")

    state = set_up_state(data, 'agent', max_time)

    for item, num in initial_items.items():
        setattr(state, item, {'agent': num})

    goals = []
    for item, num in goal_items.items():
        goals.append(('have_enough', 'agent', item, num))

    plan = pyhop.pyhop(state, goals, verbose=1)
    
    if plan is not False:
        print(f"SUCCESS: Plan found with {len(plan)} steps.")
    else:
        print("FAILURE: No plan found.")

if __name__ == '__main__':
    rules_filename = 'crafting.json'
    with open(rules_filename) as f:
        data = json.load(f)

    declare_operators(data)
    declare_methods(data)
    add_heuristic(data, 'agent')
    define_ordering(data, 'agent')

    test_cases = [
        {
            "name": "a. Given {'plank': 1}, achieve {'plank': 1} [time <= 0]",
            "initial": {'plank': 1},
            "goal": {'plank': 1},
            "time": 0
        },
        {
            "name": "b. Given {}, achieve {'plank': 1} [time <= 300]",
            "initial": {},
            "goal": {'plank': 1},
            "time": 300
        },
        {
            "name": "c. Given {'plank': 3, 'stick': 2}, achieve {'wooden_pickaxe': 1} [time <= 10]",
            "initial": {'plank': 3, 'stick': 2},
            "goal": {'wooden_pickaxe': 1},
            "time": 10
        },
        {
            "name": "d. Given {}, achieve {'iron_pickaxe': 1} [time <= 100]",
            "initial": {},
            "goal": {'iron_pickaxe': 1},
            "time": 100
        },
        {
            "name": "e. Given {}, achieve {'cart': 1, 'rail': 10} [time <= 175]",
            "initial": {},
            "goal": {'cart': 1, 'rail': 10},
            "time": 175
        },
        {
            "name": "f. Given {}, achieve {'cart': 1, 'rail': 20} [time <= 250]",
            "initial": {},
            "goal": {'cart': 1, 'rail': 20},
            "time": 250
        }
    ]

    for case in test_cases:
        solve_test_case(data, case['initial'], case['goal'], case['time'], case['name'])