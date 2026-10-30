"""No real LLM/billing: deterministic provider contract with per-attempt usage."""
import uuid
from advanced_db import initialize, connect
from advanced_budget import reserve, start_attempt, record_usage, settle

def main():
    initialize()
    operation, tenant = uuid.uuid4().hex, uuid.uuid4().hex
    reserve(operation,tenant,input_cap=500,output_cap=1000,max_attempts=2,ceiling=5000)
    for attempt, (usage, succeeded) in enumerate([(1200,False),(800,True)]):
        request_limits=start_attempt(operation,attempt,input_tokens=500)
        assert request_limits['max_output_tokens']==1000
        # Fixture has 500 input tokens; output 700/300 is within the enforced output cap.
        record_usage(operation,attempt,usage)
        print('attempt',attempt,'provider_usage',usage,'success',succeeded)
        if succeeded:
            break
    assert settle(operation)==settle(operation)==2000
    with connect() as db:
        row=db.execute('SELECT spent,reserved FROM advanced_budget_windows WHERE tenant=%s',(tenant,)).fetchone()
    print('all-attempt settlement',row)

if __name__=='__main__':
    main()
