from __future__ import annotations

from harness.task_schema import HDLTask


def _comb_truth_table(task: HDLTask) -> str:
    ids = task.id
    if ids == "local_comb_and_gate":
        return """
module tb;
  reg a, b; wire y;
  top_module dut(.a(a), .b(b), .y(y));
  initial begin
    for (integer i = 0; i < 4; i = i + 1) begin
      {a,b} = i[1:0]; #1;
      if (y !== (a & b)) $fatal(1, "and mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    if ids == "local_comb_mux2":
        return """
module tb;
  reg a, b, sel; wire y;
  top_module dut(.a(a), .b(b), .sel(sel), .y(y));
  initial begin
    for (integer i = 0; i < 8; i = i + 1) begin
      {sel,a,b} = i[2:0]; #1;
      if (y !== (sel ? b : a)) $fatal(1, "mux mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    if ids == "local_arith_half_adder":
        return """
module tb;
  reg a, b; wire sum, cout;
  top_module dut(.a(a), .b(b), .sum(sum), .cout(cout));
  initial begin
    for (integer i = 0; i < 4; i = i + 1) begin
      {a,b} = i[1:0]; #1;
      if ({cout,sum} !== (a + b)) $fatal(1, "half adder mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    if ids == "local_arith_full_adder":
        return """
module tb;
  reg a, b, cin; wire sum, cout;
  top_module dut(.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));
  initial begin
    for (integer i = 0; i < 8; i = i + 1) begin
      {a,b,cin} = i[2:0]; #1;
      if ({cout,sum} !== (a + b + cin)) $fatal(1, "full adder mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    raise ValueError(f"No truth-table generator for {task.id}")


def _with_timescale(body: str) -> str:
    return "`timescale 1ns/1ps\n" + body.lstrip()


def generate_basic_testbench(task: HDLTask) -> str:
    if task.id != "local_round_robin_arbiter2":
        return generate_testbench(task)
    return _with_timescale("""
module tb;
  reg clk=0, reset=0; reg [1:0] req=0; wire [1:0] grant;
  top_module dut(.clk(clk), .reset(reset), .req(req), .grant(grant));
  always #1 clk = ~clk;
  task step(input [1:0] r, input [1:0] exp);
    begin
      req=r; @(posedge clk); #0.1;
      if (grant !== exp) $fatal(1, "grant mismatch");
    end
  endtask
  initial begin
    reset=1; step(2'b00,2'b00); reset=0;
    step(2'b01,2'b01);
    step(2'b10,2'b10);
    step(2'b11,2'b01);
    step(2'b11,2'b10);
    step(2'b11,2'b01);
    step(2'b00,2'b00);
    step(2'b11,2'b10);
    $display("PASS"); $finish;
  end
endmodule
""")


def generate_testbench(task: HDLTask) -> str:
    def with_timescale(body: str) -> str:
        return _with_timescale(body)

    if task.expected.type == "truth_table":
        return with_timescale(_comb_truth_table(task))
    if task.id == "local_vector_reverse8":
        return with_timescale("""
module tb;
  reg [7:0] in; wire [7:0] out;
  top_module dut(.in(in), .out(out));
  function [7:0] rev(input [7:0] x);
    integer j;
    begin
      for (j = 0; j < 8; j = j + 1) rev[j] = x[7-j];
    end
  endfunction
  initial begin
    for (integer i = 0; i < 256; i = i + 1) begin
      in = i[7:0]; #1;
      if (out !== rev(in)) $fatal(1, "reverse mismatch");
    end
    $display("PASS");
  end
endmodule
""")
    if task.id == "local_popcount4":
        return with_timescale("""
module tb;
  reg [3:0] in; wire [2:0] count;
  top_module dut(.in(in), .count(count));
  function [2:0] pc(input [3:0] x);
    begin pc = x[0] + x[1] + x[2] + x[3]; end
  endfunction
  initial begin
    for (integer i = 0; i < 16; i = i + 1) begin
      in = i[3:0]; #1;
      if (count !== pc(in)) $fatal(1, "popcount mismatch");
    end
    $display("PASS");
  end
endmodule
""")
    if task.id == "local_priority_encoder4":
        return with_timescale("""
module tb;
  reg [3:0] in; wire [1:0] pos; wire valid;
  top_module dut(.in(in), .pos(pos), .valid(valid));
  reg [1:0] exp_pos; reg exp_valid;
  initial begin
    for (integer i = 0; i < 16; i = i + 1) begin
      in = i[3:0]; #1;
      exp_valid = |in;
      if (in[3]) exp_pos = 2'd3;
      else if (in[2]) exp_pos = 2'd2;
      else if (in[1]) exp_pos = 2'd1;
      else exp_pos = 2'd0;
      if (valid !== exp_valid || pos !== exp_pos) $fatal(1, "priority mismatch");
    end
    $display("PASS");
  end
endmodule
""")
    if task.id == "local_dff_sync_reset":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, d=0; wire q;
  top_module dut(.clk(clk), .reset(reset), .d(d), .q(q));
  always #1 clk = ~clk;
  initial begin
    reset=1; d=1; @(posedge clk); #0.1; if (q !== 0) $fatal(1, "reset failed");
    reset=0; d=1; @(posedge clk); #0.1; if (q !== 1) $fatal(1, "capture 1 failed");
    d=0; @(posedge clk); #0.1; if (q !== 0) $fatal(1, "capture 0 failed");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_counter_mod10":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, enable=0; wire [3:0] count;
  top_module dut(.clk(clk), .reset(reset), .enable(enable), .count(count));
  always #1 clk = ~clk;
  integer exp;
  initial begin
    reset=1; enable=1; exp=0; @(posedge clk); #0.1; if (count !== 0) $fatal(1, "reset failed");
    reset=0;
    for (integer i=0; i<25; i=i+1) begin
      @(posedge clk); exp = (exp == 9) ? 0 : exp + 1; #0.1;
      if (count !== exp[3:0]) $fatal(1, "counter mismatch");
    end
    enable=0; @(posedge clk); #0.1; if (count !== exp[3:0]) $fatal(1, "hold failed");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_edge_detect_rise":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, sig=0; wire rise;
  top_module dut(.clk(clk), .reset(reset), .sig(sig), .rise(rise));
  always #1 clk = ~clk;
  task step(input v, input exp);
    begin sig=v; @(posedge clk); #0.1; if (rise !== exp) $fatal(1, "rise mismatch"); end
  endtask
  initial begin
    reset=1; step(0,0); reset=0;
    step(0,0); step(1,1); step(1,0); step(0,0); step(1,1);
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_fsm_101_detector":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, bit_in=0; wire found;
  top_module dut(.clk(clk), .reset(reset), .bit_in(bit_in), .found(found));
  always #1 clk = ~clk;
  reg [31:0] hist;
  integer pulses = 0;
  task step(input b);
    reg exp;
    begin
      bit_in=b; @(posedge clk);
      if (reset) begin
        hist = 0;
        exp = 0;
      end else begin
        hist = {hist[30:0], b};
        exp = (hist[2:0] == 3'b101);
      end
      #0.1;
      if (found !== exp) $fatal(1, "fsm mismatch");
      if (found) pulses = pulses + 1;
    end
  endtask
  initial begin
    hist=0; pulses=0; reset=1; step(0); reset=0;
    step(1); step(0); step(1); step(0); step(1);
    if (pulses !== 2) $fatal(1, "overlap pulse count mismatch");
    step(0); step(0); step(1); step(1); step(0);
    step(1); step(0);
    reset=1; step(0); reset=0;
    hist=0;
    step(1); step(0); step(1);
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_valid_ready_skid":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, in_valid=0, out_ready=0; reg [7:0] in_data=0;
  wire in_ready, out_valid; wire [7:0] out_data;
  top_module dut(.clk(clk), .reset(reset), .in_valid(in_valid), .in_data(in_data),
                 .in_ready(in_ready), .out_valid(out_valid), .out_data(out_data),
                 .out_ready(out_ready));
  always #1 clk = ~clk;
  initial begin
    reset=1; @(posedge clk); #0.1; reset=0;
    if (!in_ready || out_valid) $fatal(1, "reset state mismatch");
    in_valid=1; in_data=8'h3c; out_ready=0; @(posedge clk); #0.1;
    if (!out_valid || out_data !== 8'h3c) $fatal(1, "did not present data");
    if (in_ready) $fatal(1, "accepted while full under backpressure");
    in_valid=0; in_data=8'ha5; repeat (3) begin @(posedge clk); #0.1;
      if (!out_valid || out_data !== 8'h3c) $fatal(1, "data not stable under backpressure");
      if (in_ready) $fatal(1, "ready high while full under backpressure");
    end
    out_ready=1; @(posedge clk); #0.1;
    if (!in_ready) $fatal(1, "ready did not recover after drain");
    in_valid=1; in_data=8'ha5; out_ready=1; @(posedge clk); #0.1;
    if (!out_valid || out_data !== 8'ha5) $fatal(1, "transparent transfer mismatch");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_fifo_sync_depth4":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, wr_en=0, rd_en=0; reg [7:0] din=0;
  wire [7:0] dout; wire full, empty;
  top_module dut(.clk(clk), .reset(reset), .wr_en(wr_en), .rd_en(rd_en),
                 .din(din), .dout(dout), .full(full), .empty(empty));
  always #1 clk = ~clk;

  reg [7:0] q [0:31];
  integer head, tail, count;

  task check_flags;
    begin
      if (empty !== (count == 0)) $fatal(1, "empty flag mismatch");
      if (full !== (count == 4)) $fatal(1, "full flag mismatch");
    end
  endtask

  task cycle(input w, input r, input [7:0] data);
    reg [7:0] exp_dout;
    reg expect_read;
    begin
      exp_dout = q[head];
      expect_read = r && (count > 0);
      wr_en=w; rd_en=r; din=data; @(posedge clk); #0.1;
      if (expect_read && dout !== exp_dout) $fatal(1, "dout mismatch");
      if (expect_read) begin head = head + 1; count = count - 1; end
      if (w && count < 4) begin q[tail] = data; tail = tail + 1; count = count + 1; end
      check_flags();
    end
  endtask

  initial begin
    head=0; tail=0; count=0;
    reset=1; @(posedge clk); #0.1; reset=0; check_flags();
    cycle(1,0,8'h11); cycle(1,0,8'h22); cycle(1,0,8'h33); cycle(1,0,8'h44);
    if (!full) $fatal(1, "expected full");
    cycle(1,0,8'h55);
    cycle(0,1,8'h00); cycle(1,1,8'h55); cycle(0,1,8'h00); cycle(0,1,8'h00);
    cycle(0,1,8'h00); cycle(0,1,8'h00);
    if (!empty) $fatal(1, "expected empty");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_round_robin_arbiter2":
        return with_timescale("""
module tb;
  reg clk=0, reset=0; reg [1:0] req=0; wire [1:0] grant;
  top_module dut(.clk(clk), .reset(reset), .req(req), .grant(grant));
  always #1 clk = ~clk;

  integer covered_both_01 = 0;
  integer covered_both_10 = 0;
  integer covered_idle_after_grant = 0;
  integer covered_reset_reentry = 0;
  integer seed = 32'h1234abcd;
  integer i;

  task check_invariants;
    begin
      if ((grant & ~req) !== 2'b00) $fatal(1, "grant to inactive requester");
      if (grant === 2'b11) $fatal(1, "grant must be onehot0");
      if (req === 2'b00 && grant !== 2'b00) $fatal(1, "idle grant mismatch");
      if (req === 2'b01 && grant !== 2'b01) $fatal(1, "single requester 0 mismatch");
      if (req === 2'b10 && grant !== 2'b10) $fatal(1, "single requester 1 mismatch");
      if (req === 2'b11 && grant === 2'b01) covered_both_01 = 1;
      if (req === 2'b11 && grant === 2'b10) covered_both_10 = 1;
    end
  endtask

  task step(input [1:0] r, input [1:0] exp);
    begin
      req=r; @(posedge clk); #0.1;
      if (grant !== exp) $fatal(1, "grant mismatch");
      check_invariants();
    end
  endtask

  task step_any(input [1:0] r);
    begin
      req=r; @(posedge clk); #0.1;
      check_invariants();
    end
  endtask

  initial begin
    reset=1; step(2'b00,2'b00); reset=0;
    step(2'b01,2'b01);
    step(2'b10,2'b10);
    step(2'b11,2'b01);
    reset=1; step(2'b00,2'b00); reset=0;
    covered_reset_reentry = 1;
    step(2'b11,2'b01);
    step(2'b11,2'b10);
    step(2'b11,2'b01);
    step(2'b00,2'b00);
    covered_idle_after_grant = 1;
    step(2'b11,2'b10);
    step(2'b11,2'b01);
    step(2'b11,2'b10);

    step_any(2'b01);
    step_any(2'b00);
    step_any(2'b10);
    step_any(2'b11);
    step_any(2'b00);
    step_any(2'b11);
    step_any(2'b01);
    step_any(2'b10);

    for (i = 0; i < 32; i = i + 1) begin
      seed = (seed * 1103515245 + 12345);
      step_any(seed[1:0]);
    end

    if (!covered_both_01 || !covered_both_10) $fatal(1, "both-request coverage missing");
    if (!covered_idle_after_grant) $fatal(1, "idle-after-grant coverage missing");
    if (!covered_reset_reentry) $fatal(1, "reset reentry coverage missing");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_round_robin_arbiter2_enable":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, enable=0; reg [1:0] req=0; wire [1:0] grant;
  top_module dut(.clk(clk), .reset(reset), .enable(enable), .req(req), .grant(grant));
  always #1 clk = ~clk;

  task check_invariants;
    begin
      if ((grant & ~req) !== 2'b00) $fatal(1, "grant to inactive requester");
      if (grant === 2'b11) $fatal(1, "grant must be onehot0");
      if (!enable && grant !== 2'b00) $fatal(1, "disabled grant mismatch");
      if (enable && req === 2'b00 && grant !== 2'b00) $fatal(1, "idle grant mismatch");
      if (enable && req === 2'b01 && grant !== 2'b01) $fatal(1, "single requester 0 mismatch");
      if (enable && req === 2'b10 && grant !== 2'b10) $fatal(1, "single requester 1 mismatch");
    end
  endtask

  task step(input en, input [1:0] r, input [1:0] exp);
    begin
      enable=en; req=r; @(posedge clk); #0.1;
      if (grant !== exp) $fatal(1, "grant mismatch");
      check_invariants();
    end
  endtask

  initial begin
    reset=1; step(0,2'b00,2'b00); reset=0;
    step(1,2'b11,2'b01);
    step(0,2'b11,2'b00);
    step(0,2'b11,2'b00);
    step(1,2'b11,2'b10);
    step(1,2'b01,2'b01);
    step(1,2'b00,2'b00);
    step(1,2'b11,2'b01);
    reset=1; step(1,2'b11,2'b00); reset=0;
    step(1,2'b11,2'b01);
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_valid_ready_pipeline2":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, in_valid=0, out_ready=0; reg [7:0] in_data=0;
  wire in_ready, out_valid; wire [7:0] out_data;
  top_module dut(.clk(clk), .reset(reset), .in_valid(in_valid), .in_data(in_data),
                 .in_ready(in_ready), .out_valid(out_valid), .out_data(out_data),
                 .out_ready(out_ready));
  always #1 clk = ~clk;

  task step(input iv, input [7:0] data, input ordy);
    begin
      in_valid=iv; in_data=data; out_ready=ordy; @(posedge clk); #0.1;
    end
  endtask

  initial begin
    reset=1; step(0,8'h00,0); reset=0;
    step(1,8'h10,0);
    step(1,8'h20,0);
    if (!out_valid || out_data !== 8'h10) $fatal(1, "first item not visible");
    if (in_ready) $fatal(1, "pipeline should be full");
    repeat (3) begin
      step(1,8'h30,0);
      if (!out_valid || out_data !== 8'h10) $fatal(1, "data changed under stall");
    end
    step(0,8'h00,1); if (!out_valid || out_data !== 8'h20) $fatal(1, "second item missing");
    step(1,8'h30,1); if (!out_valid || out_data !== 8'h30) $fatal(1, "third item missing");
    step(0,8'h00,1); if (out_valid) $fatal(1, "pipeline should be empty");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_mul4_shift_add":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, start=0; reg [3:0] a=0, b=0;
  wire [7:0] product; wire busy, done;
  top_module dut(.clk(clk), .reset(reset), .start(start), .a(a), .b(b),
                 .product(product), .busy(busy), .done(done));
  always #1 clk = ~clk;

  task tick;
    begin @(posedge clk); #0.1; end
  endtask

  task run_case(input [3:0] aa, input [3:0] bb);
    integer cycles;
    begin
      a=aa; b=bb; start=1; tick(); start=0;
      cycles=0;
      while (!done && cycles < 12) begin
        if (!busy && cycles < 3) $fatal(1, "busy dropped too early");
        tick(); cycles = cycles + 1;
      end
      if (!done) $fatal(1, "done timeout");
      if (product !== aa * bb) $fatal(1, "product mismatch");
      tick(); if (done) $fatal(1, "done not one-cycle pulse");
    end
  endtask

  initial begin
    reset=1; tick(); reset=0;
    run_case(4'd0, 4'd9);
    run_case(4'd3, 4'd5);
    run_case(4'd15, 4'd15);
    $display("PASS"); $finish;
  end
endmodule
""")
    raise ValueError(f"No testbench generator for {task.id}")
