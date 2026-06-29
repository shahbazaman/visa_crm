from visa_crm.api.communication_event import create_communication_event

from visa_crm.api.evaluation import create_employee_evaluation

from visa_crm.api.score_history import create_score_history

from visa_crm.api.kpi import update_employee_kpi

from visa_crm.api.leaderboard import update_leaderboard




def process_call(call_doc):


    event = create_communication_event(

        call_doc

    )



    call_doc.communication_event = event





    create_employee_evaluation(

        call_doc

    )




    create_score_history(

        call_doc

    )




    update_employee_kpi(

        call_doc.employee_match

    )




    update_leaderboard()


