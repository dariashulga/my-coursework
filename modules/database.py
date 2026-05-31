# modules/database.py

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

from config import DATABASE_PATH

db_dir = os.path.dirname(DATABASE_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

Base = declarative_base()


class AnalysisResult(Base):
    __tablename__ = 'analysis_results'

    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True)
    domain = Column(String)
    title = Column(String)
    date = Column(DateTime)
    reliability_score = Column(Integer, default=0)
    uniqueness_score = Column(Float, default=0.0)
    is_original_source = Column(Boolean, default=False)
    analysis_date = Column(DateTime, default=datetime.now)
    keyword = Column(String, nullable=True)

engine = create_engine(f'sqlite:///{DATABASE_PATH}', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def save_analysis_result(article_data):
    session = Session()
    try:
        existing = session.query(AnalysisResult).filter_by(url=article_data['url']).first()
        if existing:
            existing.reliability_score = article_data['reliability_score']
            existing.uniqueness_score = article_data['uniqueness_score']
            existing.is_original_source = article_data.get('is_original_source', False)
            existing.analysis_date = datetime.now()
        else:
            result = AnalysisResult(
                url=article_data['url'],
                domain=article_data['domain'],
                title=article_data['title'],
                date=article_data['date'],
                reliability_score=article_data['reliability_score'],
                uniqueness_score=article_data['uniqueness_score'],
                is_original_source=article_data.get('is_original_source', False),
                keyword=article_data.get('keyword')
            )
            session.add(result)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"❌ Ошибка сохранения: {e}")
    finally:
        session.close()


def get_all_results():
    session = Session()
    results = session.query(AnalysisResult).all()
    session.close()
    return results


def get_original_source_for_topic(keyword=None):
    session = Session()
    query = session.query(AnalysisResult).filter_by(is_original_source=True)
    if keyword:
        query = query.filter_by(keyword=keyword)
    result = query.first()
    session.close()
    return result


def delete_all_results():
    session = Session()
    try:
        session.query(AnalysisResult).delete()
        session.commit()
    except:
        session.rollback()
    finally:
        session.close()