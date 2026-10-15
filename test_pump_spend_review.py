from pump_spend_review import review_instructions, PUMP_PROGRAM, COMPUTE_PROGRAM, ATA_PROGRAM
W='w'; M='m'
def ins(p,d,accounts=None,i=0):
    return {'index':i,'program':p,'data_hex':d,'accounts':accounts or []}
def test_decodes_without_approving():
    tx={'lookup_tables':[{'table':'a'}], 'instructions':[
      ins(COMPUTE_PROGRAM,'0210980200'),
      ins(COMPUTE_PROGRAM,'03c7e5000000000000'),
      ins(ATA_PROGRAM,'01',[W,'ata',W,M]),
      ins(PUMP_PROGRAM,'66323d1201daebea3988163e07000000c8d1a100000000003200',[W,M]) ]}
    r=review_instructions(tx,wallet=W,mint=M)
    assert r['max_priority_fee_lamports_from_compute_budget']==10000
    assert r['instructions'][-1]['unverified_u64_at_offset_16']==10605000
    assert not r['max_swap_debit_verified']
    assert not r['approved_for_execution']
def test_unknown_program_blocks():
    r=review_instructions({'lookup_tables':[{'table':'a'}], 'instructions':[ins('evil','')]},wallet=W,mint=M)
    assert any('Unexpected instruction program' in x for x in r['blocking_reasons'])
    assert not r['approved_for_execution']
