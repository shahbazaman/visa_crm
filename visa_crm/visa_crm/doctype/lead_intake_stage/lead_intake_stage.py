from frappe.model.document import Document
from visa_crm.api.stage_definitions import STAGE_BY_NAME,STAGE_STATES

class LeadIntakeStage(Document):
    def before_insert(self):
        self.stage_key=self.stage_key or f"{self.queue}:{self.stage}"

    def validate(self):
        if self.stage not in STAGE_BY_NAME:
            raise ValueError(f"Unknown lead intake stage: {self.stage}")
        if self.state not in STAGE_STATES:
            raise ValueError(f"Unknown lead intake stage state: {self.state}")
        definition=STAGE_BY_NAME[self.stage]
        self.sequence=definition["sequence"]
        self.requirement_class=definition["requirement_class"]
        self.parent_stage=definition.get("parent_stage")
        if self.max_attempts is None:
            self.max_attempts=definition["max_attempts"]
