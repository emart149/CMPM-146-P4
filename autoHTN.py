import pyhop
import json
import time

def check_enough(state, ID, item, num):
    if getattr(state, item)[ID] >= num:
        return []

    # Forces an upgrade to a better tool if we need a lot of resources
    if item in ('cobble', 'coal') and num >= 8 and getattr(state, 'stone_pickaxe')[ID] < 1:
        return [('have_enough', ID, 'stone_pickaxe', 1), ('produce', ID, item), ('have_enough', ID, item, num)]

    return [('produce_enough', ID, item, num)]

def produce_enough(state, ID, item, num):
    return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)

def produce(state, ID, item):
    return [('produce_{}'.format(item), ID)]

pyhop.declare_methods('produce', produce)

def tool_select(tool_checks, fallback):
    """
    Back to what we talked about last night with the tools. Cart was failing because it tried to use wooden tools
    when it really needed stone or better. It kept on retrying with wooden tools and failing. This is why the time was going backwards.
    tool_checks: List of tuples (tool_name, op_name)
    fallback: Function that returns the default task list if no tool is found
    """
    def method(state, ID):
        # Check every tool in the priority list
        for tool, op in tool_checks:
            if getattr(state, tool)[ID] >= 1:
                return [(op, ID)]
        # If we have none, do the fallback
        return fallback(ID)
    return method

# 1. Define tools and gathering wood.
wood_tools = [
    ('iron_axe', 'op_iron_axe_for_wood'),
    ('stone_axe', 'op_stone_axe_for_wood'),
    ('wooden_axe', 'op_wooden_axe_for_wood')
]
# Wood falls back to punching
m_wood = tool_select(wood_tools, lambda ID: [('op_punch_for_wood', ID)])

# 2. Define picks for cobble/coal (same tools, different ops)
# Note: These fall back to CRAFTING a wooden pickaxe, not punching
def pick_fallback(op_name):
    return lambda ID: [('have_enough', ID, 'wooden_pickaxe', 1), (op_name, ID)]

cobble_tools = [
    ('iron_pickaxe', 'op_iron_pickaxe_for_cobble'),
    ('stone_pickaxe', 'op_stone_pickaxe_for_cobble'),
    ('wooden_pickaxe', 'op_wooden_pickaxe_for_cobble')
]
m_cobble = tool_select(cobble_tools, pick_fallback('op_wooden_pickaxe_for_cobble'))

coal_tools = [
    ('iron_pickaxe', 'op_iron_pickaxe_for_coal'),
    ('stone_pickaxe', 'op_stone_pickaxe_for_coal'),
    ('wooden_pickaxe', 'op_wooden_pickaxe_for_coal')
]
m_coal = tool_select(coal_tools, pick_fallback('op_wooden_pickaxe_for_coal'))

# 3. Ore (requires stone))
ore_tools = [
    ('iron_pickaxe', 'op_iron_pickaxe_for_ore'),
    ('stone_pickaxe', 'op_stone_pickaxe_for_ore')
]
# Ore falls back to stone pickaxe
m_ore = tool_select(ore_tools, lambda ID: [('have_enough', ID, 'stone_pickaxe', 1), ('op_stone_pickaxe_for_ore', ID)])


def set_order(consumes, depth_stack):
    items = list(consumes.keys())
    if len(items) <= 1:
        return items

    item_set = set(items)

    # adjacency: x -> y if x depends on y and both are in the consumes set
    adj = {
        x: [y for y in depth_stack.get(x, set()) if y in item_set and y != x]
        for x in items
    }

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {x: WHITE for x in items}
    out = []

    def dfs(x):
        color[x] = GRAY
        for y in adj[x]:
            if color[y] == GRAY:
                return False  
            if color[y] == WHITE and not dfs(y):
                return False
        color[x] = BLACK
        out.append(x)
        return True

    for x in items:
        if color[x] == WHITE:
            if not dfs(x):
                return items  

    out.reverse()
    return out

def make_method(name, rule, tools=None, consumes_order=None):
    prod = rule.get("Produces", {})
    req  = rule.get("Requires", {})
    cons = rule.get("Consumes", {})
    t_c  = rule.get("Time", 0)

    if consumes_order is None:
        consumes_order = list(cons.keys())

    def tier(tool_name):
        if tool_name.startswith("wooden_"): return 1
        if tool_name.startswith("stone_"):  return 2
        if tool_name.startswith("iron_"):   return 3
        if tool_name in ("bench", "furnace"): return 0
        return 0

    required_tool_tier = 0
    for item in req:
        if item in (tools or set()):
            required_tool_tier = max(required_tool_tier, tier(item))

    def method(state, ID):
        subtasks = []

        for item, amount in req.items():
            subtasks.append(('have_enough', ID, item, amount))

        for item in consumes_order:
            subtasks.append(('have_enough', ID, item, cons[item]))

        op_name = 'op_{}'.format(name.replace(' ', '_'))
        subtasks.append((op_name, ID))
        return subtasks

    method.__name__ = 'method_{}'.format(name.replace(' ', '_'))

    method._meta = {
        "tier": required_tool_tier,
        "time": t_c,
        "n_subtasks": 1 + len(req) + len(cons),
        "produces": list(prod.keys())
    }
    return method

def declare_methods(data):
    tools = set(data.get("Tools", [])) | {"bench", "furnace"}

    dep_map = {}
    for rule in data['Recipes'].values():
        for p in rule.get('Produces', {}):
            dep_map.setdefault(p, set()).update(rule.get("Consumes", {}).keys())

    rec_prod = {}

    for rec_name, rule in data['Recipes'].items():
        for product in rule['Produces']:
            if product not in rec_prod:
                rec_prod[product] = []

            cons = rule.get("Consumes", {})
            cons_order = set_order(cons, dep_map)

            # Forces ingot before stick if both in recipe
            if 'ingot' in cons and 'stick' in cons:
                cons_order = (
                    ['ingot']
                    + [x for x in cons_order if x not in ('ingot', 'stick')]
                    + ['stick']
                )

            mth = make_method(rec_name, rule, tools=tools, consumes_order=cons_order)
            rec_prod[product].append(mth)

    for product, method_list in rec_prod.items():
        method_list.sort(key=lambda m: (m._meta["tier"], m._meta["time"], m._meta["n_subtasks"]))
        pyhop.declare_methods('produce_{}'.format(product), *method_list)

    pyhop.declare_methods("produce_wood", m_wood)
    pyhop.declare_methods("produce_cobble", m_cobble)
    pyhop.declare_methods("produce_coal", m_coal)
    pyhop.declare_methods("produce_ore", m_ore)

def make_operator(rule):
    prod = rule.get("Produces", {})
    req = rule.get("Requires", {})
    cons = rule.get("Consumes", {})
    t_c = rule.get("Time", 0)

    def operator(state, ID):
        if state.time[ID] < t_c:
            return False

        for item, amt in req.items():
            if getattr(state, item)[ID] < amt:
                return False

        for item, amt in cons.items():
            if getattr(state, item)[ID] < amt:
                return False

        state.time[ID] -= t_c
        
        for item, amt in cons.items():
            curr = getattr(state, item)[ID]
            setattr(state, item, {ID: curr - amt})

        for item, amt in prod.items():
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
    # prune search branch if heuristic() returns True
    # do not change parameters to heuristic(), but can add more heuristic functions with the same parameters:
    # e.g. def heuristic2
    tools = set(data.get("Tools", [])) | {"bench", "furnace"}

    def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
        if depth > 1000:
            return True

        task_name = curr_task[0]
        
        if task_name.startswith('produce_'):
            product = task_name.replace('produce_', '')
            
            if product in tools and getattr(state, product)[ID] >= 1:
                return True

            if product in tools:
                for upstream_task in calling_stack:
                     if upstream_task[0] == task_name:
                         return True
                         
        return False

    pyhop.add_check(heuristic)

# Unused
# def define_ordering(data, ID):
#     def reorder_methods(state, curr_task, tasks, plan, depth, calling_stack, methods):
#         return methods
#     pyhop.define_ordering(reorder_methods)

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

    goals = [('have_enough', 'agent', item, num) for item, num in goal_items.items()]

    op_time = {}
    for recipe_name, rule in data['Recipes'].items():
        op_name = "op_" + recipe_name.replace(' ', '_')
        op_time[op_name] = rule.get('Time', 0)

    t0 = time.perf_counter()
    plan = pyhop.pyhop(state, goals, verbose=1)
    t1 = time.perf_counter()
    runtime_sec = t1 - t0

    if plan is not False:
        total_time_used = sum(op_time.get(action[0], 0) for action in plan)
        time_remaining = max_time - total_time_used

        print(f"SUCCESS: Plan found with {len(plan)} steps.")
        print(f"Time cost: {total_time_used}  |  Remainging time: {time_remaining}")
    else:
        print("FAILURE: No plan found.")


if __name__ == '__main__':
    rules_filename = 'crafting.json'
    with open(rules_filename) as f:
        data = json.load(f)

    declare_operators(data)
    declare_methods(data)
    add_heuristic(data, 'agent')
    # define_ordering(data, 'agent')

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
        },
        {
            "name": "custom. Given {}, achieve {'cart': 3, 'rail': 48} [time <= 450]",
            "initial": {},
            "goal": {'cart': 3, 'rail': 48},
            "time": 450
        }
    ]

    for case in test_cases:
        solve_test_case(data, case['initial'], case['goal'], case['time'], case['name'])
    #pyhop.print_operators()
    #pyhop.print_methods()