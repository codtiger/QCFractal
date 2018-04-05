class DaskNanny(object):
    """
    This object can add to the Dask queue and watches for finished jobs. Jobs that are finished
    are automatically posted to the associated MongoDB and removed from the queue.
    """

    def __init__(self, queue_socket, mongod_socket, logger=None):

        self.queue_socket = queue_socket
        self.mongod_socket = mongod_socket
        self.queue = {}
        self.errors = {}

        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger('DaskNanny')

    def add_future(self, future):
        uid = str(uuid.uuid4())
        self.queue[uid] = future
        self.logger.info("MONGO ADD: FUTURE %s" % uid)
        return uid

    def update(self):
        del_keys = []
        for key, future in self.queue.items():
            if future.done():
                try:
                    tmp_data = future.result()
                    if not tmp_data["success"]:
                        raise ValueError("Computation (%s, %s) did not complete successfully!:\n%s\n" %
                                         (tmp_data["molecule_hash"], tmp_data["modelchem"], tmp_data["error"]))
                    # res = self.mongod_socket.del_page_by_data(tmp_data)
                    res = self.mongod_socket.add_page(tmp_data)
                    self.logger.info("MONGO ADD: (%s, %s) - %s" % (tmp_data["molecule_hash"], tmp_data["modelchem"],
                                                                   str(res)))
                except Exception as e:
                    ename = str(type(e).__name__) + ":" + str(e)
                    msg = "".join(traceback.format_tb(e.__traceback__))
                    msg += str(type(e).__name__) + ":" + str(e)
                    self.errors[key] = msg
                    self.logger.info("MONGO ADD: ERROR\n%s" % msg)

                del_keys.append(key)

        for key in del_keys:
            del self.queue[key]

class DaskScheduler(tornado.web.RequestHandler):
    """
    Takes in a data packet the contains the molecule_hash, modelchem and options objects.
    """

    def initialize(self, **objects):
        self.objects = objects

        if "logger" in list(self.objects):
            self.logger = self.objects["logger"]
        else:
            self.logger = logging.getLogger('Scheduler')

    def post(self):

        # Decode the data
        data = json.loads(self.request.body.decode('utf-8'))
        header = self.request.headers
        _check_auth(self.objects, self.request.headers)

        # Grab objects
        self.objects["mongod_socket"].set_project(header["project"])
        dask = self.objects["queue_socket"]
        queue_nanny = self.objects["queue_nanny"]

        tasks, program = _unpack_tasks(data, self.objects["mongod_socket"], self.logger)

        # Submit
        ret = {}
        ret["error"] = []
        ret["Nanny ID"] = []
        for task in tasks:
            if "internal_error" in list(task):
                ret["error"].append(task["internal_error"])
                continue
            fut = dask.submit(compute.computers[program], task)
            ret["Nanny ID"].append(self.objects["queue_nanny"].add_future(fut))

        # Return anything of interest
        ret["success"] = True
        self.write(json.dumps(ret))

    def get(self):

        header = self.request.headers
        _check_auth(self.objects, self.request.headers)

        self.objects["mongod_socket"].set_project(header["project"])
        queue_nanny = self.objects["queue_nanny"]
        ret = {}
        ret["queue"] = list(queue_nanny.queue)
        ret["error"] = queue_nanny.errors
        self.write(json.dumps(ret))

class FireworksScheduler(tornado.web.RequestHandler):
    """
    Takes in a data packet the contains the molecule_hash, modelchem and options objects.
    """

    def initialize(self, **objects):
        self.objects = objects

        if "logger" in list(self.objects):
            self.logger = self.objects["logger"]
        else:
            self.logger = logging.getLogger('Scheduler')

    def post(self):
        # Fireworks
        import fireworks

        # Decode the data
        data = json.loads(self.request.body.decode('utf-8'))
        header = self.request.headers
        _check_auth(self.objects, self.request.headers)

        # Grab objects
        self.objects["mongod_socket"].set_project(header["project"])
        lpad = self.objects["queue_socket"]
        queue_nanny = self.objects["queue_nanny"]

        tasks, program = _unpack_tasks(data, self.objects["mongod_socket"], self.logger)

        # Submit
        ret = {}
        ret["error"] = []
        ret["Nanny ID"] = []
        for task in tasks:
            if "internal_error" in list(task):
                ret["error"].append(task["internal_error"])
                continue
            fw = fireworks.Firework(
                fireworks.PyTask(func="dqm_compute.run_psi4", args=[task], stored_data_varname="results"))
            launches = lpad.add_wf(fw)
            fws_id = list(launches.values())[0]

            ret["Nanny ID"].append(self.objects["queue_nanny"].add_future(fws_id))

        # Return anything of interest
        ret["success"] = True
        self.write(json.dumps(ret))

    def get(self):

        header = self.request.headers
        _check_auth(self.objects, self.request.headers)

        self.objects["mongod_socket"].set_project(header["project"])
        queue_nanny = self.objects["queue_nanny"]
        ret = {}
        ret["queue"] = list(queue_nanny.queue)
        ret["error"] = queue_nanny.errors
        self.write(json.dumps(ret))
