from sqlalchemy import Column, Integer, String, Text, ForeignKey
from app.db.database import Base

class CAPA(Base):
    __tablename__ = "capa"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"))
    root_cause = Column(Text, nullable=True)
    corrective_action = Column(Text, nullable=True)
    preventive_action = Column(Text, nullable=True)
    status = Column(String, default="Pending")