"""
    tests.test_fetching
    ~~~~~~~~~~~~~~~~~~~

    Provides tests for fetching resources from endpoints generated by
    Flask-Restless.

    This module includes tests for additional functionality that is not already
    tested by :mod:`test_jsonapi`, the module that guarantees Flask-Restless
    meets the minimum requirements of the JSON API specification.

    :copyright: 2015 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com> and
                contributors.
    :license: GNU AGPLv3+ or BSD

"""
from datetime import datetime
from datetime import time

try:
    from flask.ext.sqlalchemy import SQLAlchemy
except:
    has_flask_sqlalchemy = False
else:
    has_flask_sqlalchemy = True
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Time
from sqlalchemy import Unicode
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from flask.ext.restless import APIManager
from flask.ext.restless import CONTENT_TYPE
from flask.ext.restless import ProcessingException
from flask.ext.restless.helpers import to_dict

from .helpers import DatabaseTestBase
from .helpers import FlaskTestBase
from .helpers import loads
from .helpers import MSIE8_UA
from .helpers import MSIE9_UA
from .helpers import ManagerTestBase
from .helpers import skip_unless
from .helpers import unregister_fsa_session_signals


class TestFetching(ManagerTestBase):
    """Tests for fetching resources."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestFetching, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode, primary_key=True)

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            bedtime = Column(Time)
            birth_datetime = Column(DateTime)
            birthday = Column(Date)

            @hybrid_property
            def has_early_bedtime(self):
                if hasattr(self, 'bedtime'):
                    if self.bedtime is None:
                        return False
                    nine_oclock = time(21)
                    return self.bedtime < nine_oclock
                return False

        class Tag(self.Base):
            __tablename__ = 'tag'
            name = Column(Unicode, primary_key=True)

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)

            @classmethod
            def query(cls):
                return self.session.query(cls).filter(cls.id < 2)

        class User(self.Base):
            __tablename__ = 'user'
            id = Column(Integer, primary_key=True)
            email = Column(Unicode, primary_key=True)

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Tag = Tag
        self.User = User
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Comment)
        self.manager.create_api(Person)
        self.manager.create_api(Tag)

    def test_serialize_time(self):
        """Test for getting the JSON representation of a time field."""
        now = datetime.now().time()
        person = self.Person(id=1, bedtime=now)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['bedtime'] == now.isoformat()

    def test_serialize_datetime(self):
        """Test for getting the JSON representation of a datetime field."""
        now = datetime.now()
        person = self.Person(id=1, birth_datetime=now)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['birth_datetime'] == now.isoformat()

    def test_serialize_date(self):
        """Test for getting the JSON representation of a date field."""
        now = datetime.now().date()
        person = self.Person(id=1, birthday=now)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['birthday'] == now.isoformat()

    def test_jsonp(self):
        """Test for a JSON-P callback on a single resource request."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        response = self.app.get('/api/person/1?callback=foo')
        assert response.data.startswith(b'foo(')
        assert response.data.endswith(b')')
        document = loads(response.data[4:-1])
        person = document['data']
        assert person['id'] == '1'

    def test_jsonp_collection(self):
        """Test for a JSON-P callback on a collection of resources."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        response = self.app.get('/api/person?callback=foo')
        assert response.data.startswith(b'foo(')
        assert response.data.endswith(b')')
        document = loads(response.data[4:-1])
        people = document['data']
        assert ['1', '2'] == sorted(person['id'] for person in people)

    def test_alternate_primary_key(self):
        """Tests that models with primary keys that are not named ``id`` are
        are still accessible via their primary keys.

        """
        tag = self.Tag(name=u'foo')
        self.session.add(tag)
        self.session.commit()
        response = self.app.get('/api/tag/foo')
        document = loads(response.data)
        tag = document['data']
        assert tag['id'] == 'foo'

    def test_primary_key_int_string(self):
        """Tests for getting a resource that has a string primary key,
        including the possibility of a string representation of a number.

        """
        tag = self.Tag(name=u'1')
        self.session.add(tag)
        self.session.commit()
        response = self.app.get('/api/tag/1')
        document = loads(response.data)
        tag = document['data']
        assert tag['name'] == '1'
        assert tag['id'] == '1'

    # TODO Not supported right now.
    #
    # def test_specified_primary_key(self):
    #     """Tests that models with more than one primary key are accessible via
    #     a primary key specified by the server.

    #     """
    #     article = self.Article(id=1, title='foo')
    #     self.session.add(article)
    #     self.session.commit()
    #     self.manager.create_api(self.Article, url_prefix='/api2',
    #                             primary_key='title')
    #     response = self.app.get('/api2/article/1')
    #     assert response.status_code == 404
    #     response = self.app.get('/api2/article/foo')
    #     assert response.status_code == 200
    #     document = loads(response.data)
    #     resource = document['data']
    #     # Resource objects must have string IDs.
    #     assert resource['id'] == str(article.id)
    #     assert resource['title'] == article.title

    def test_correct_content_type(self):
        """Tests that the server responds with :http:status:`200` if the
        request has the correct JSON API content type.

        """
        response = self.app.get('/api/person', content_type=CONTENT_TYPE)
        assert response.status_code == 200
        assert response.headers['Content-Type'] == CONTENT_TYPE

    def test_no_content_type(self):
        """Tests that the server responds with :http:status:`415` if the
        request has no content type.

        """
        response = self.app.get('/api/person', content_type=None)
        assert response.status_code == 415
        assert response.headers['Content-Type'] == CONTENT_TYPE

    def test_wrong_content_type(self):
        """Tests that the server responds with :http:status:`415` if the
        request has the wrong content type.

        """
        bad_content_types = ('application/json', 'application/javascript')
        for content_type in bad_content_types:
            response = self.app.get('/api/person', content_type=content_type)
            assert response.status_code == 415
            assert response.headers['Content-Type'] == CONTENT_TYPE

    def test_msie8(self):
        """Tests for compatibility with Microsoft Internet Explorer 8.

        According to issue #267, making requests using JavaScript from MSIE8
        does not allow changing the content type of the request (it is always
        ``text/html``). Therefore Flask-Restless should ignore the content type
        when a request is coming from this client.

        """
        headers = {'User-Agent': MSIE8_UA}
        content_type = 'text/html'
        response = self.app.get('/api/person', headers=headers,
                                content_type=content_type)
        assert response.status_code == 200

    def test_msie9(self):
        """Tests for compatibility with Microsoft Internet Explorer 9.

        According to issue #267, making requests using JavaScript from MSIE9
        does not allow changing the content type of the request (it is always
        ``text/html``). Therefore Flask-Restless should ignore the content type
        when a request is coming from this client.

        """
        headers = {'User-Agent': MSIE9_UA}
        content_type = 'text/html'
        response = self.app.get('/api/person', headers=headers,
                                content_type=content_type)
        assert response.status_code == 200

    def test_callable_query(self):
        """Tests for making a query with a custom callable ``query`` attribute.

        For more information, see pull request #133.

        """
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        self.session.add_all([comment1, comment2])
        self.session.commit()
        response = self.app.get('/api/comment')
        document = loads(response.data)
        print(document)
        comments = document['data']
        assert ['1'] == sorted(comment['id'] for comment in comments)

    def test_hybrid_property(self):
        """Tests for fetching a resource with a hybrid property attribute."""
        person1 = self.Person(id=1, bedtime=time(20))
        person2 = self.Person(id=2, bedtime=time(22))
        self.session.add_all([person1, person2])
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        assert person['has_early_bedtime']
        response = self.app.get('/api/person/2')
        document = loads(response.data)
        person = document['data']
        assert not person['has_early_bedtime']

    # TODO does this even make sense?
    def test_group_by(self):
        """Tests for grouping a collection of resources according to a field.

        """
        article1 = self.Article(id=1, title='foo')
        article2 = self.Article(id=2, title='bar')
        article3 = self.Article(id=3, title='foo')
        self.session.add_all([article1, article2, article3])
        self.session.commit()
        response = self.app.get('/api/article?sort=-id&group=title')
        document = loads(response.data)
        articles = document['data']
        assert False, 'Not implemented'

    def test_collection_name_single(self):
        """Tests for fetching a single resource with an alternate collection
        name.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person, collection_name='people')
        response = self.app.get('/api/people/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['id'] == '1'
        assert person['type'] == 'people'

    def test_collection_name_multiple(self):
        """Tests for fetching multiple resources with an alternate collection
        name.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person, collection_name='people')
        response = self.app.get('/api/people')
        assert response.status_code == 200
        document = loads(response.data)
        people = document['data']
        assert len(people) == 1
        person = people[0]
        assert person['id'] == '1'
        assert person['type'] == 'people'

    def test_custom_serialization(self):
        """Tests for a custom serialization function."""
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        def serializer(instance):
            result = to_dict(instance)
            result['foo'] = 'bar'
            return result

        self.manager.create_api(self.Person, serializer=serializer)
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        assert person['foo'] == 'bar'


class TestProcessors(DatabaseTestBase):
    """Tests for pre- and postprocessors."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestProcessors, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person)

    def test_single_resource_processing_exception(self):
        """Tests for a preprocessor that raises a :exc:`ProcessingException`
        when fetching a single resource.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        def forbidden(**kw):
            raise ProcessingException(code=403, description='forbidden')

        preprocessors = dict(GET_RESOURCE=[forbidden])
        self.manager.create_api(self.Person, preprocessors=preprocessors)
        response = self.app.get('/api/person/1')
        assert response.status_code == 403
        document = loads(response.data)
        errors = document['errors']
        assert len(errors) == 1
        error = errors[0]
        assert 'forbidden' == error['detail']

    def test_collection_processing_exception(self):
        """Tests for a preprocessor that raises a :exc:`ProcessingException`
        when fetching a collection of resources.

        """

        def forbidden(**kw):
            raise ProcessingException(code=403, description='forbidden')

        preprocessors = dict(GET_COLLECTION=[forbidden])
        self.manager.create_api(self.Person, preprocessors=preprocessors)
        response = self.app.get('/api/person')
        assert response.status_code == 403
        document = loads(response.data)
        errors = document['errors']
        assert len(errors) == 1
        error = errors[0]
        assert 'forbidden' == error['detail']

    def test_change_id(self):
        """Tests that a return value from a preprocessor overrides the ID of
        the resource to fetch as given in the request URL.

        """
        person = self.Person(id=1, name='foo')
        self.session.add(person)
        self.session.commit()

        def increment_id(instance_id=None, **kw):
            if instance_id is None:
                raise ProcessingException(code=400)
            return int(instance_id) + 1

        preprocessors = dict(GET_RESOURCE=[increment_id])
        self.manager.create_api(self.Person, preprocessors=preprocessors)
        response = self.app.get('/api/person/0')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['id'] == '1'
        assert person['name'] == 'foo'

    def test_last_preprocessor_changes_id(self):
        """Tests that a return value from the last preprocessor in the list
        overrides the ID of the resource to fetch as given in the request URL.

        """
        person = self.Person(id=2, name='foo')
        self.session.add(person)
        self.session.commit()

        def increment_id(instance_id=None, **kw):
            if instance_id is None:
                raise ProcessingException(code=400)
            return int(instance_id) + 1

        preprocessors = dict(GET_RESOURCE=[increment_id, increment_id])
        self.manager.create_api(self.Person, preprocessors=preprocessors)
        response = self.app.get('/api/person/0')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['id'] == '2'
        assert person['name'] == 'foo'

    def test_no_client_filters(self):
        """Tests that a preprocessor can modify the filter objects in a
        request, even if the client did not specify any ``filter[objects]``
        query parameter.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()

        def restrict_ids(filters=None, **kw):
            """Adds an additional filter to any existing filters that restricts
            which resources appear in the response.

            """
            if filters is None:
                raise ProcessingException(code=400)
            filt = dict(name='id', op='lt', val=2)
            filters.append(filt)

        preprocessors = dict(GET_COLLECTION=[restrict_ids])
        self.manager.create_api(self.Person, preprocessors=preprocessors)
        response = self.app.get('/api/person')
        assert response.status_code == 200
        document = loads(response.data)
        people = document['data']
        assert ['1'] == sorted(person['id'] for person in people)

    def test_add_filters(self):
        """Tests that a preprocessor can modify the filter objects provided by
        the client in the ``filter[objects]`` query parameter.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        self.session.add_all([person1, person2, person3])
        self.session.commit()

        def restrict_ids(filters=None, **kw):
            """Adds an additional filter to any existing filters that restricts
            which resources appear in the response.

            """
            if filters is None:
                raise ProcessingException(code=400)
            filt = dict(name='id', op='lt', val=2)
            filters.append(filt)

        preprocessors = dict(GET_COLLECTION=[restrict_ids])
        self.manager.create_api(self.Person, preprocessors=preprocessors)
        filters = [dict(name='id', op='in', val=[1, 3])]
        query = {'filter[objects]': filters}
        response = self.app.get('/api/person', query_string=query)
        assert response.status_code == 200
        document = loads(response.data)
        people = document['data']
        assert ['1'] == sorted(person['id'] for person in people)

    def test_collection_postprocessor(self):
        """Tests that a postprocessor for a collection endpoint has access to
        the filters specified by the client.

        """
        client_filters = [dict(name='id', op='eq', val=1)]

        def check_filters(filters=None, **kw):
            """Assert that the filters that Flask-Restless understood from the
            request are the same filter objects provided by the client.

            """
            assert filters == client_filters

        postprocessors = dict(GET_COLLECTION=[check_filters])
        self.manager.create_api(self.Person, postprocessors=postprocessors)
        query_string = {'filter[objects]': client_filters}
        response = self.app.search('/api/person', query_string=query_string)
        assert response.status_code == 200


class TestDynamicRelationships(ManagerTestBase):
    """Tests for fetching resources from dynamic to-many relationships."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestDynamicRelationships, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('articles',
                                                            lazy='dynamic'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Article = Article
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)

    def test_to_one(self):
        """Tests for fetching a resource with a dynamic link to a to-one
        relation.

        """
        article = self.Article(id=1)
        person = self.Person(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        author = article['links']['author']['linkage']
        assert author['id'] == '1'
        assert author['type'] == 'person'

    def test_to_many(self):
        """Tests for fetching a resource with a dynamic link to a to-many
        relation.

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        article1.author = person
        article2.author = person
        self.session.add_all([person, article1, article2])
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        links = person['links']
        articles = links['articles']['linkage']
        assert ['1', '2'] == sorted(article['id'] for article in articles)

    def test_related_resource_url(self):
        """Tests for fetching a resource with a dynamic link to a to-many
        relation from the related resource URL.

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        article1.author = person
        article2.author = person
        self.session.add_all([person, article1, article2])
        self.session.commit()
        response = self.app.get('/api/person/1/articles')
        document = loads(response.data)
        articles = document['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)
        assert all(article['type'] == 'article' for article in articles)

    def test_relationship_url(self):
        """Tests for fetching a resource with a dynamic link to a to-many
        relation from the relationship URL.

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        article1.author = person
        article2.author = person
        self.session.add_all([person, article1, article2])
        self.session.commit()
        response = self.app.get('/api/person/1/links/articles')
        document = loads(response.data)
        articles = document['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)
        assert all(article['type'] == 'article' for article in articles)


class TestAssociationProxy(ManagerTestBase):
    """Tests for getting an object with a relationship using an association
    proxy.

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask.ext.restless.manager.APIManager` for that application,
        and creates the ReSTful API endpoints for the models used in the test
        methods.

        """
        super(TestAssociationProxy, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            tags = association_proxy('articletags', 'tag',
                                     creator=lambda tag: ArticleTag(tag=tag))
            # tag_names = association_proxy('tags', 'name',
            #                               creator=lambda name: Tag(name=name))

        class ArticleTag(self.Base):
            __tablename__ = 'articletag'
            article_id = Column(Integer, ForeignKey('article.id'),
                                primary_key=True)
            article = relationship(Article, backref=backref('articletags'))
            tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
            tag = relationship('Tag')
            # extra_info = Column(Unicode)

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        self.Article = Article
        self.Tag = Tag
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        # HACK Need to create APIs for these other models because otherwise
        # we're not able to create the link URLs to them.
        #
        # TODO Fix this by simply not creating links to related models for
        # which no API has been made.
        self.manager.create_api(Tag)
        self.manager.create_api(ArticleTag)

    def test_fetch(self):
        """Test for fetching a resource that has a many-to-many relation that
        uses an association proxy.

        """
        article = self.Article(id=1)
        tag = self.Tag(id=1)
        article.tags.append(tag)
        self.session.add_all([article, tag])
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        links = article['links']
        tags = links['tags']['linkage']
        assert ['1'] == sorted(tag['id'] for tag in tags)

    def test_scalar(self):
        """Tests for fetching an association proxy to scalars as a list
        attribute instead of a link object.

        """
        article = self.Article(id=1)
        tag1 = self.Tag(name='foo')
        tag2 = self.Tag(name='bar')
        article.tags = [tag1, tag2]
        self.session.add_all([article, tag1, tag2])
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        assert ['bar', 'foo'] == sorted(article['tag_names'])


@skip_unless(has_flask_sqlalchemy, 'Flask-SQLAlchemy not found.')
class TestFlaskSqlalchemy(FlaskTestBase):
    """Tests for fetching resources defined as Flask-SQLAlchemy models instead
    of pure SQLAlchemy models.

    """

    def setUp(self):
        """Creates the Flask-SQLAlchemy database and models."""
        super(TestFlaskSqlalchemy, self).setUp()
        self.db = SQLAlchemy(self.flaskapp)
        self.session = self.db.session

        class Person(self.db.Model):
            id = self.db.Column(self.db.Integer, primary_key=True)

        self.Person = Person
        self.db.create_all()
        self.manager = APIManager(self.flaskapp, flask_sqlalchemy_db=self.db)
        self.manager.create_api(self.Person)

    def tearDown(self):
        """Drops all tables and unregisters Flask-SQLAlchemy session signals.

        """
        self.db.drop_all()
        unregister_fsa_session_signals()

    def test_fetch_resource(self):
        """Test for fetching a resource."""
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        assert person['id'] == '1'
        assert person['type'] == 'person'

    def test_fetch_collection(self):
        """Test for fetching a collection of resource."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        response = self.app.get('/api/person')
        document = loads(response.data)
        people = document['data']
        assert ['1', '2'] == sorted(person['id'] for person in people)
