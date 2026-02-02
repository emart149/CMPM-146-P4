import pyhop
import json
import time
import sys

def check_enough(state, ID, item, num):
    if getattr(state, item)[ID] >= num: 
        return []
    return False

def produce_enough(state, ID, item, num):
    return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)

def produce(state, ID, item):
    return [(f'produce_{item}', ID)]

pyhop.declare_methods('produce', produce)

def make_method(name, rule):
    def method(state, ID):
        subtasks = []

        # 1) Requirements first (tools/bench)
        if 'Requires' in rule:
            for item, amount in rule['Requires'].items():
                subtasks.append(('have_enough', ID, item, amount))

        # 2) Consumables (materials)
        if 'Consumes' in rule:
            sorted_items = sorted(rule['Consumes'].items(), key=lambda x: x[0], reverse=True)
            for item, amount in sorted_items:
                subtasks.append(('have_enough', ID, item, amount))

        # 3) Finally, the operator
        op_name = 'op_{}'.format(name.replace(' ', '_'))
        subtasks.append((op_name, ID))

        return subtasks

    method.__name__ = 'method_{}'.format(name.replace(' ', '_'))
    return method

def declare_methods(data):
    rec_prod = {}

    for rec_name, rule in data['Recipes'].items():
        for product in rule['Produces']:
            rec_prod.setdefault(product, []).append({
                'name': rec_name,
                'rule': rule,
                'time': rule.get('Time', 1)
            })

    def method_sort_key(rec_info):
        name = rec_info['name'].lower()
        rule = rec_info['rule']
        t = rec_info['time']

        produces = rule.get('Produces', {})

        # 1) WOOD: punch first
        if 'wood' in produces:
            if 'punch' in name:
                return (0, t)
            if 'wooden_axe' in name:
                return (1, t)
            if 'stone_axe' in name:
                return (2, t)
            if 'iron_axe' in name:
                return (3, t)
            return (4, t)

        # 2) COBBLE: wooden pickaxe first
        if 'cobble' in produces:
            if 'wooden_pickaxe' in name:
                return (0, t)
            if 'stone_pickaxe' in name:
                return (1, t)
            if 'iron_pickaxe' in name:
                return (2, t)
            return (3, t)

        # 3) ORE/COAL: wooden pickaxe first
        if 'ore' in produces or 'coal' in produces:
            if 'wooden_pickaxe' in name:
                return (0, t)
            if 'stone_pickaxe' in name:
                return (1, t)
            if 'iron_pickaxe' in name:
                return (2, t)
            return (3, t)

        # 4) Everything else: prefer fewer requirements
        req = rule.get('Requires', {})
        req_score = sum(req.values()) if isinstance(req, dict) else 0
        return (10 + req_score, t)

    for product, rec_list in rec_prod.items():
        rec_list.sort(key=method_sort_key)

        method_list = []
        for rec_info in rec_list:
            method_list.append(make_method(rec_info['name'], rec_info['rule']))

        pyhop.declare_methods(f'produce_{product}', *method_list)

def make_operator(rule):
    def operator(state, ID):
        # Check time
        if state.time[ID] < rule['Time']:
            return False
        
        # Check requirements
        if 'Requires' in rule:
            for item, amt in rule['Requires'].items():
                if getattr(state, item)[ID] < amt:
                    return False
        
        # Check consumables
        if 'Consumes' in rule:
            for item, amt in rule['Consumes'].items():
                if getattr(state, item)[ID] < amt:
                    return False
        
        # Apply changes
        state.time[ID] -= rule['Time']
        
        if 'Consumes' in rule:
            for item, amt in rule['Consumes'].items():
                getattr(state, item)[ID] -= amt
        
        for item, amt in rule['Produces'].items():
            getattr(state, item)[ID] += amt
        
        return state
    
    return operator

def declare_operators(data):
    operators_list = []
    for recipe_name in data['Recipes']:
        new_operator = make_operator(data['Recipes'][recipe_name])
        new_operator.__name__ = "op_" + recipe_name.replace(' ', '_')
        operators_list.append(new_operator)

    pyhop.declare_operators(*operators_list)

def set_up_state(data, ID, time=0):
    state = pyhop.State('state')
    state.time = {ID: time}

    # Initialize all items from Items and Tools lists
    all_items = []
    if 'Items' in data:
        all_items.extend(data['Items'])
    if 'Tools' in data:
        all_items.extend(data['Tools'])
    
    # Remove duplicates
    all_items = list(set(all_items))
    
    # Initialize all to 0
    for item in all_items:
        setattr(state, item, {ID: 0})

    # Set initial values
    if 'Problem' in data and 'Initial' in data['Problem']:
        for item, num in data['Problem']['Initial'].items():
            if hasattr(state, item):
                getattr(state, item)[ID] = num

    return state

def solve_test_case(data, initial_items, goal_items, max_time, case_name, verbose=0, timeout=30):
    print(f"\n{'='*20} Solving Case: {case_name} {'='*20}")
    print(f"Initial: {initial_items}")
    print(f"Goal: {goal_items}")
    print(f"Time Limit: {max_time}")

    # Create state
    state = set_up_state(data, 'agent', max_time)
    
    # Set initial items
    for item, num in initial_items.items():
        if hasattr(state, item):
            getattr(state, item)['agent'] = num
        else:
            setattr(state, item, {'agent': num})

    # Create goals
    goals = []
    for item, num in goal_items.items():
        goals.append(('have_enough', 'agent', item, num))

    # Run planner with timeout
    start_time = time.time()
    plan = False
    
    try:
        # Set up timeout
        import signal
        
        class TimeoutException(Exception):
            pass
        
        def timeout_handler(signum, frame):
            raise TimeoutException()
        
        # Set the signal handler
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)
        
        try:
            plan = pyhop.pyhop(state, goals, verbose=verbose)
        except TimeoutException:
            print(f"TIMEOUT: Planning exceeded {timeout} seconds")
            plan = False
        finally:
            signal.alarm(0)  # Disable the alarm
            
    except Exception as e:
        print(f"Error during planning: {e}")
        plan = False
    
    elapsed = time.time() - start_time
    
    if plan is not False:
        print(f"SUCCESS: Plan found with {len(plan)} steps in {elapsed:.2f}s")
        
        # Calculate time used
        total_time = 0
        for action in plan:
            action_name = action[0]
            for recipe_name, rule in data['Recipes'].items():
                op_name = "op_" + recipe_name.replace(' ', '_')
                if op_name == action_name:
                    total_time += rule.get('Time', 1)
                    break
        
        print(f"Time used: {total_time}, Time remaining: {state.time['agent']}")
        
        # Show plan
        if len(plan) <= 50:
            print(f"Plan ({len(plan)} steps):")
            for i, action in enumerate(plan):
                print(f"  {i+1}. {action}")
        else:
            print(f"Plan has {len(plan)} steps (showing first 30):")
            for i, action in enumerate(plan[:30]):
                print(f"  {i+1}. {action}")
            print(f"  ... and {len(plan)-30} more steps")
        
        # Verify plan
        test_state = set_up_state(data, 'test', max_time)
        for item, num in initial_items.items():
            if hasattr(test_state, item):
                getattr(test_state, item)['test'] = num
        
        for action in plan:
            action_name = action[0]
            for recipe_name, rule in data['Recipes'].items():
                op_name = "op_" + recipe_name.replace(' ', '_')
                if op_name == action_name:
                    test_state.time['test'] -= rule['Time']
                    if 'Consumes' in rule:
                        for item, amt in rule['Consumes'].items():
                            if hasattr(test_state, item):
                                getattr(test_state, item)['test'] -= amt
                    for item, amt in rule['Produces'].items():
                        if hasattr(test_state, item):
                            getattr(test_state, item)['test'] += amt
                    break
        
        all_goals_met = True
        for item, num in goal_items.items():
            if not (hasattr(test_state, item) and getattr(test_state, item)['test'] >= num):
                all_goals_met = False
        
        if all_goals_met:
            print("✓ Plan verification: PASSED")
        else:
            print("✗ Plan verification: FAILED")
            
    else:
        if elapsed >= timeout:
            print(f"TIMEOUT: No plan found in {timeout}s (elapsed: {elapsed:.2f}s)")
        else:
            print(f"FAILURE: No plan found in {elapsed:.2f}s")
        
        # Show current state to debug
        print("\nCurrent resource state:")
        key_items = ['wood', 'plank', 'stick', 'bench', 'cobble', 'wooden_pickaxe', 
                    'stone_pickaxe', 'iron_pickaxe', 'furnace', 'ore', 'coal', 'ingot',
                    'cart', 'rail', 'iron_axe', 'stone_axe', 'wooden_axe']
        for item in key_items:
            if hasattr(state, item):
                print(f"  {item}: {getattr(state, item)['agent']}")
    
    return plan is not False, plan

if __name__ == '__main__':
    rules_filename = 'crafting.json'
    with open(rules_filename) as f:
        data = json.load(f)

    print("Initializing HTN planner with optimized method ordering...")
    
    # Increase recursion limit
    sys.setrecursionlimit(10000)
    
    declare_operators(data)
    declare_methods(data)
    # NO HEURISTICS, NO MODIFICATIONS - just plain pyhop
    
    # Test cases
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
            "name": "e. Given {}, achieve {'cart': 1} [time <= 175]",
            "initial": {},
            "goal": {'cart': 1},
            "time": 175
        },
        {
            "name": "f. Given {}, achieve {'cart': 1} [time <= 250]",
            "initial": {},
            "goal": {'cart': 1},
            "time": 250
        }
    ]

    # Run test cases
    for i, case in enumerate(test_cases):
        print(f"\n{'#'*60}")
        print(f"TEST CASE {i+1}: {case['name']}")
        print(f"{'#'*60}")
        
        # Adjust settings based on complexity
        if i < 3:  # Cases a, b, c
            verbose = 2
            timeout = 10
        else:  # Cases d, e, f
            verbose = 0  # No verbose output for complex cases
            timeout = 30  # 30 seconds for complex cases
            
        success, plan = solve_test_case(data, case['initial'], case['goal'], 
                                       case['time'], case['name'], verbose=verbose, timeout=timeout)
        
        if not success and i >= 3:  # For complex cases d-f
            print("\nNote: Complex cases might require more time or better search strategies")