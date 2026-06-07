module top_module(
    input logic clk,
    input logic reset,
    input logic in_valid,
    input logic [7:0] in_data,
    output logic in_ready,
    output logic out_valid,
    output logic [7:0] out_data,
    input logic out_ready
);
    logic [7:0] data_q;

    assign in_ready = out_ready;
    assign out_valid = in_valid && out_ready;
    assign out_data = out_ready ? in_data : data_q;

    always_ff @(posedge clk) begin
        if (reset) begin
            data_q <= 8'h00;
        end else if (in_valid) begin
            data_q <= in_data;
        end
    end
endmodule
