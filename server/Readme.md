# HTTP Server

**Status: not implemented.** This folder holds the design notes for hosting the Trae agent as an HTTP
server. It contains no code: there is nothing in here to start, import, or deploy, and no module of
this repository serves HTTP. The only entry point Trae Agent installs today is `trae-cli`; the
programmatic interface behind it is the `Agent` class in `trae_agent/agent/agent.py`, whose `run`
method the Roadmap below is written around.

If you want Trae Agent over HTTP, the open feature requests to watch or comment on are #148, #250 and
#350. If you want to build it, the sections below are the shape the server is expected to take --
implement against them rather than starting the discussion over.

## Expected Features of the HTTP Server

1. The server should be able to perform stateless operations.
2. The server should be able to handle concurrent requests.
3. The server should always respond in JSON format, even if the response is streaming.

## Additional Features Expected

1. The server should be able to reproduce or repeat actions based on a specific JSON file. For example, given a trajectory, it could reproduce specific steps and follow new steps produced by another model.
2. To ensure requests are dynamic, the server should support different models, different requests, and different output formats based on the request JSON file.

## Roadmap

1. To build a fully functional HTTP Trae agent, we need to gradually split the `trae_agent` into more component-based modules and add more features to make it more dynamic. A specific task is to see if the `run` function can accept an additional parameter called `model`.
2. Besides the `run` function, other functions should be callable not only via CLI but also through the HTTP server to meet the second requirement.
3. To handle concurrent requests, it is also necessary to ensure the HTTP server is stateless — at least when handling the `run` function operating in different folders.
