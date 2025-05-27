--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.5

--
-- Name: auth_provider_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.auth_provider_enum AS ENUM (
    'EMAIL'
);


ALTER TYPE public.auth_provider_enum OWNER TO ananaz;

--
-- Name: identifier_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.identifier_type_enum AS ENUM (
    'NIN',
    'NHS'
);


ALTER TYPE public.identifier_type_enum OWNER TO ananaz;

--
-- Name: user_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.user_status_enum AS ENUM (
    'PENDING_VERIFICATION',
    'VERIFIED',
    'VERIFICATION_FAILED',
    'BLOCKED',
    'REGISTERED'
);


ALTER TYPE public.user_status_enum OWNER TO ananaz;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: ananaz
--

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
                              id uuid NOT NULL,
                              email character varying NOT NULL,
                              password character varying,
                              status public.user_status_enum NOT NULL,
                              "phoneNumber" character varying,
                              "identifierType" public.identifier_type_enum,
                              "identifierValue" character varying,
                              auth_provider public.auth_provider_enum NOT NULL
);


ALTER TABLE public.users OWNER TO ananaz;

--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: ananaz
--

COPY public.alembic_version (version_num) FROM stdin;



--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, email, password, status, "phoneNumber", "identifierType", "identifierValue", auth_provider) FROM stdin;



--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: ananaz
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: ix_users_auth_provider; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_users_auth_provider ON public.users USING btree (auth_provider);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_identifierType; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX "ix_users_identifierType" ON public.users USING btree ("identifierType");


--
-- Name: ix_users_identifierValue; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX "ix_users_identifierValue" ON public.users USING btree ("identifierValue");


--
-- Name: ix_users_phoneNumber; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX "ix_users_phoneNumber" ON public.users USING btree ("phoneNumber");


--
-- Name: ix_users_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_users_status ON public.users USING btree (status);


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: ananaz
--

ALTER DEFAULT PRIVILEGES FOR ROLE ananaz IN SCHEMA public GRANT ALL ON TABLES TO ananaz;


--
-- PostgreSQL database dump complete
--

